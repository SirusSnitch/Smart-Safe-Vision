# ============================================================================
# YOLO_DETECT_TASK.PY - Multi-model detection, OCR only on best.pt detections
# ============================================================================

import base64
import cv2
import numpy as np
import torch
from ultralytics import YOLO
from celery import shared_task
import redis
import time
import gc
import os
import math
import logging
from typing import Optional
from django.apps import apps
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.utils import timezone
from django.core.files.base import ContentFile
from gismap.tasks.ocr_task import run_ocr_task

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

current_dir = os.path.dirname(__file__)

# --- YOLODetector class ---
class YOLODetector:
    def __init__(self, model_path: str):
        self.model_path = model_path
        self.model = None
        self.load_model()

    def load_model(self):
        if not os.path.exists(self.model_path):
            raise FileNotFoundError(f"Modèle non trouvé: {self.model_path}")
        try:
            device = "cuda" if torch.cuda.is_available() else "cpu"
            self.model = YOLO(self.model_path).to(device)
            logger.info(f"✅ Modèle YOLO chargé sur {device.upper()}: {self.model_path}")
        except Exception as e:
            logger.error(f"❌ Erreur chargement modèle: {e}")
            raise

    def detect_plates(self, frame: np.ndarray, conf_threshold: float = 0.25) -> tuple:
        try:
            results = self.model.predict(
                source=frame,
                save=False,
                conf=conf_threshold,
                device='cuda' if torch.cuda.is_available() else 'cpu',
                imgsz=(640, 384),
                verbose=False
            )
            detections = []
            for result in results:
                if result.boxes is not None:
                    for box in result.boxes:
                        x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                        confidence = float(box.conf[0])
                        detections.append({
                            'bbox': (x1, y1, x2, y2),
                            'confidence': confidence
                        })
            return detections, results
        except Exception as e:
            logger.error(f"Erreur détection YOLO: {e}")
            return [], None

# --- Load models ---
model_path_best = os.path.abspath(os.path.join(current_dir, "..", "yolo", "best.pt"))
model_path_box = os.path.abspath(os.path.join(current_dir, "..", "yolo", "box.pt"))
model_path_pose = os.path.abspath(os.path.join(current_dir, "..", "yolo", "yolov8s-pose.pt"))

detector_best = YOLODetector(model_path_best)
detector_box = YOLODetector(model_path_box)
pose_detector = YOLO(model_path_pose)  # pose model loaded directly, no wrapper

# --- Redis connection ---
try:
    r = redis.StrictRedis(host='localhost', port=6379, db=0, socket_timeout=5)
    r.ping()
    logger.info("✅ Connexion Redis établie")
except redis.ConnectionError:
    logger.error("❌ Impossible de se connecter à Redis")
    raise

# --- Helper: decode frame from Redis ---
def decode_frame_from_redis(encoded_frame: bytes) -> Optional[np.ndarray]:
    try:
        img_data = base64.b64decode(encoded_frame + b'=' * (-len(encoded_frame) % 4))
        np_arr = np.frombuffer(img_data, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        return frame
    except Exception as e:
        logger.error(f"Erreur décodage frame: {e}")
        return None

# --- WebSocket notification ---
def send_unauthorized_notification(matricule_data):
    try:
        channel_layer = get_channel_layer()
        if channel_layer:
            notification_data = {
                'type': 'send_notification',
                'data': {
                    'alert_type': 'unauthorized_plate',
                    'matricule': matricule_data['numero'],
                    'camera': matricule_data['camera_name'],
                    'location': matricule_data.get('location', 'Inconnue'),
                    'timestamp': timezone.now().isoformat(),
                    'confidence': matricule_data.get('confidence_score', 0),
                    'message': f"🚨 Matricule non autorisée: {matricule_data['numero']}"
                }
            }
            async_to_sync(channel_layer.group_send)('notifications', notification_data)
            logger.info(f"📢 Notification envoyée: {matricule_data['numero']}")
    except Exception as e:
        logger.error(f"❌ Erreur notification WebSocket: {e}")

# --- DB save/check ---
def check_and_save_detection(license_plate, camera_id, confidence_score, image_bytes=None):
    try:
        DetectionMatricule = apps.get_model('gismap', 'DetectionMatricule')
        MatriculeAutorise = apps.get_model('gismap', 'MatriculeAutorise')
        Camera = apps.get_model('gismap', 'Camera')

        camera = Camera.objects.get(id=camera_id)
        is_authorized = False
        if camera.department:
            is_authorized = MatriculeAutorise.objects.filter(numero=license_plate, lieu=camera.department).exists()

        detection = DetectionMatricule.objects.create(
            numero=license_plate,
            camera=camera,
            est_autorise=is_authorized
        )

        if image_bytes:
            filename = f"{timezone.now().strftime('%Y%m%d_%H%M%S')}_{license_plate}.jpg"
            detection.image.save(filename, ContentFile(image_bytes), save=True)

        if not is_authorized:
            matricule_data = {
                'numero': license_plate,
                'camera_name': camera.name,
                'location': camera.department.name if camera.department else 'Inconnue',
                'confidence_score': confidence_score,
                'detection_id': detection.id
            }
            send_unauthorized_notification(matricule_data)
            logger.warning(f"🚨 ALERTE: Matricule non autorisée {license_plate} (Cam: {camera.name})")
        else:
            logger.info(f"✅ Matricule autorisée: {license_plate} (Cam: {camera.name})")

        return detection, is_authorized

    except Exception as e:
        logger.error(f"❌ Erreur vérification matricule: {e}")
        return None, False

# --- Process detections ---
def process_detections(frame: np.ndarray, detections: list, camera_id: int, run_ocr: bool) -> np.ndarray:
    annotated_frame = frame.copy()
    for detection in detections:
        x1, y1, x2, y2 = detection['bbox']
        confidence = detection['confidence']
        width, height = x2 - x1, y2 - y1
        if width < 50 or height < 20:
            continue
        margin = 5
        x1_crop = max(0, x1 - margin)
        y1_crop = max(0, y1 - margin)
        x2_crop = min(frame.shape[1], x2 + margin)
        y2_crop = min(frame.shape[0], y2 + margin)
        cropped = frame[y1_crop:y2_crop, x1_crop:x2_crop]
        if cropped.size > 0 and run_ocr:
            _, buffer = cv2.imencode('.jpg', cropped, [cv2.IMWRITE_JPEG_QUALITY, 95])
            image_bytes = buffer.tobytes()
            run_ocr_task.delay(image_bytes, camera_id)
        cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(annotated_frame, f'{confidence:.2f}', (x1, y1 - 10), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    return annotated_frame

# --- Pose helpers ---
def get_angle(a, b, c):
    ba = a - b
    bc = c - b
    cosine_angle = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc))
    angle = np.arccos(np.clip(cosine_angle, -1.0, 1.0))
    return np.degrees(angle)

def get_torso_angle(p1, p2):
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    return abs(math.degrees(math.atan2(dy, dx)))

def is_fallen(keypoints, image_height):
    k = keypoints[:, :2]
    l_sh, r_sh = k[5], k[6]
    l_hip, r_hip = k[11], k[12]
    mid_sh = (l_sh + r_sh) / 2
    mid_hip = (l_hip + r_hip) / 2
    torso_angle = get_torso_angle(mid_sh, mid_hip)
    w, h = max(k[:, 0]) - min(k[:, 0]), max(k[:, 1]) - min(k[:, 1])
    horizontal = w > h
    center_y = np.mean(k[:, 1])
    low_center = center_y > image_height * 0.6
    return (torso_angle < 30 or torso_angle > 150) and horizontal and low_center

def is_fight_aggression(keypoints):
    k = keypoints[:, :2]

    nose = k[0]
    l_wrist, r_wrist = k[9], k[10]
    l_elbow, r_elbow = k[7], k[8]
    l_shoulder, r_shoulder = k[5], k[6]
    l_hip, r_hip = k[11], k[12]

    def dist(a, b): return np.linalg.norm(a - b)

    lw_head_close = dist(l_wrist, nose) < 80
    rw_head_close = dist(r_wrist, nose) < 80

    lw_shoulder_close = dist(l_wrist, l_shoulder) < 100
    rw_shoulder_close = dist(r_wrist, r_shoulder) < 100

    l_arm_angle = get_angle(l_shoulder, l_elbow, l_wrist)
    r_arm_angle = get_angle(r_shoulder, r_elbow, r_wrist)
    elbows_bent = (l_arm_angle < 120 and r_arm_angle < 120)

    mid_shoulder = (l_shoulder + r_shoulder) / 2
    mid_hip = (l_hip + r_hip) / 2
    torso_angle = get_torso_angle(mid_shoulder, mid_hip)
    leaning_forward = 70 < torso_angle < 110

    close_arms = (lw_head_close and lw_shoulder_close) or (rw_head_close and rw_shoulder_close)
    return close_arms and elbows_bent and leaning_forward

def classify_pose(result, image_height):
    persons = []
    if result.keypoints is None:
        return persons
    for kp in result.keypoints.data.cpu().numpy():
        label = "Normal"
        if is_fallen(kp, image_height):
            label = "Fallen"
        elif is_fight_aggression(kp):
            label = "Aggression"
        persons.append((label, kp))
    return persons

# --- Main detection task ---
@shared_task
def detect_from_redis(camera_id: int, max_iterations: int = 1000):
    logger.info(f"🚀 Démarrage détection YOLO pour caméra {camera_id}")
    iterations = 0
    consecutive_errors = 0
    max_consecutive_errors = 10
    try:
        while iterations < max_iterations:
            encoded_frame = r.get(f"camera_frame_{camera_id}")
            if not encoded_frame:
                time.sleep(0.5)
                continue
            frame = decode_frame_from_redis(encoded_frame)
            if frame is None:
                consecutive_errors += 1
                if consecutive_errors > max_consecutive_errors:
                    break
                continue
            consecutive_errors = 0

            frame = cv2.resize(frame, (640, 384))

            # --- Detect with best.pt and box.pt ---
            detections_best, _ = detector_best.detect_plates(frame)
            detections_box, _ = detector_box.detect_plates(frame)

            annotated_frame = frame.copy()

            if detections_best:
                annotated_frame = process_detections(frame, detections_best, camera_id, run_ocr=True)
                logger.info(f"🎯 {len(detections_best)} plaque(s) détectée(s) par best.pt (Cam {camera_id})")
            else:
                logger.info(f"🎯 Aucune plaque détectée par best.pt (Cam {camera_id})")

            if detections_box:
                annotated_frame = process_detections(annotated_frame, detections_box, camera_id, run_ocr=False)
                logger.info(f"📦 {len(detections_box)} objet(s) détecté(s) par box.pt (Cam {camera_id})")
            else:
                logger.info(f"📦 Aucun objet détecté par box.pt (Cam {camera_id})")

            # --- Pose detection & annotation ---
            pose_results = pose_detector.predict(
                source=frame,
                conf=0.5,
                device='cuda' if torch.cuda.is_available() else 'cpu',
                verbose=False
            )

            persons = classify_pose(pose_results[0], frame.shape[0])

            for label, kp in persons:
                x0, y0 = kp[0][:2]
                if x0 == 0 and y0 == 0:
                    x0 = int((kp[5][0] + kp[6][0]) / 2)
                    y0 = int((kp[5][1] + kp[6][1]) / 2)
                color = (0, 0, 255) if label == "Fallen" else (0, 165, 255) if label == "Aggression" else (0, 255, 0)
                cv2.putText(annotated_frame, label, (int(x0), int(y0) - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
                cv2.circle(annotated_frame, (int(x0), int(y0)), 5, (255, 0, 0), -1)

            if os.getenv('ENABLE_DISPLAY', 'true').lower() == 'true':
                cv2.imshow(f"🎯 Caméra {camera_id}", annotated_frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

            torch.cuda.empty_cache()
            gc.collect()
            time.sleep(0.1)
            iterations += 1
    except Exception as e:
        logger.error(f"❌ Erreur: {e}")
    finally:
        cv2.destroyAllWindows()
        logger.info(f"🧹 Fin détection caméra {camera_id}")
        return {"camera_id": camera_id, "iterations_completed": iterations, "status": "completed"}
