# ============================================================================
# YOLO_DETECT_TASK.PY - Version optimisée avec intégration WebSocket et OCR
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
import logging
from typing import Optional
# NOUVEAUX IMPORTS POUR WEBSOCKET
from django.apps import apps
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.utils import timezone
from django.core.files.base import ContentFile
from gismap.tasks.ocr_task import run_ocr_task

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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


    def detect_plates(self, frame: np.ndarray, conf_threshold: float = 0.25) -> list:
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

current_dir = os.path.dirname(__file__)
model_path = os.path.abspath(os.path.join(current_dir, "..", "yolo", "best.pt"))
detector = YOLODetector(model_path)

try:
    r = redis.StrictRedis(host='localhost', port=6379, db=0, socket_timeout=5)
    r.ping()
    logger.info("✅ Connexion Redis établie")
except redis.ConnectionError:
    logger.error("❌ Impossible de se connecter à Redis")
    raise

def decode_frame_from_redis(encoded_frame: bytes) -> Optional[np.ndarray]:
    try:
        img_data = base64.b64decode(encoded_frame + b'=' * (-len(encoded_frame) % 4))
        np_arr = np.frombuffer(img_data, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        return frame
    except Exception as e:
        logger.error(f"Erreur décodage frame: {e}")
        return None

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

def process_detections(frame: np.ndarray, detections: list, camera_id: int) -> np.ndarray:

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
        if cropped.size > 0:
            _, buffer = cv2.imencode('.jpg', cropped, [cv2.IMWRITE_JPEG_QUALITY, 95])
            image_bytes = buffer.tobytes()
            run_ocr_task.delay(image_bytes, camera_id)
        cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(annotated_frame, f'{confidence:.2f}', (x1, y1-10), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    return annotated_frame

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
            detections, yolo_results = detector.detect_plates(frame)
            if detections:
                logger.info(f"🎯 {len(detections)} plaque(s) détectée(s) (Cam {camera_id})")
                annotated_frame = process_detections(frame, detections, camera_id)
            else:
                annotated_frame = frame
            if os.getenv('ENABLE_DISPLAY', 'true').lower() == 'true':
                cv2.imshow(f"🎯 Caméra {camera_id}", annotated_frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
            if yolo_results:
                del yolo_results
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
