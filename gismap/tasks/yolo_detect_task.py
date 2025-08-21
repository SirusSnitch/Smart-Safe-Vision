# ============================================================================ 
# YOLO_DETECT_TASK.PY - Multi-model detection, OCR only on best.pt detections
# WebSocket streaming at ~1 FPS, duplicate frames skipped
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
import hashlib
from typing import Optional
from django.utils import timezone
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from gismap.tasks.ocr_task import run_ocr_task
from tensorflow.keras.models import load_model

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

current_dir = os.path.dirname(__file__)

# ============================================================================ 
# YOLO Detector Wrapper
# ============================================================================
class YOLODetector:
    def __init__(self, model_path: str):
        self.model_path = model_path
        self.model = None
        self.load_model()

    def load_model(self):
        if not os.path.exists(self.model_path):
            raise FileNotFoundError(f"Modèle non trouvé: {self.model_path}")
        device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = YOLO(self.model_path).to(device)
        logger.info(f"✅ YOLO chargé sur {device.upper()}: {self.model_path}")

    def detect(self, frame: np.ndarray, conf_threshold: float = 0.25):
        try:
            results = self.model.predict(
                source=frame,
                save=False,
                conf=conf_threshold,
                device="cuda" if torch.cuda.is_available() else "cpu",
                imgsz=(640, 384),
                verbose=False
            )
            detections = []
            for result in results:
                if result.boxes is not None:
                    for box in result.boxes:
                        x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                        conf = float(box.conf[0])
                        cls_id = int(box.cls[0])
                        cls_name = self.model.names[cls_id] if hasattr(self.model, "names") else str(cls_id)
                        detections.append({
                            "bbox": (x1, y1, x2, y2),
                            "confidence": conf,
                            "class_name": cls_name
                        })
            return detections, results
        except Exception as e:
            logger.error(f"❌ YOLO detect() error: {e}")
            return [], None

# ============================================================================ 
# FireNet Detector
# ============================================================================
class FireNetDetector:
    def __init__(self, model_path: str):
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Modèle FireNet non trouvé: {model_path}")
        self.model = load_model(model_path)
        logger.info(f"✅ FireNet chargé: {model_path}")

    def predict_fire(self, frame: np.ndarray) -> float:
        try:
            img = cv2.resize(frame, (128, 128))
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB) / 255.0
            img = np.expand_dims(img, axis=0)
            return float(self.model.predict(img)[0][0])
        except Exception as e:
            logger.error(f"❌ FireNet predict() error: {e}")
            return 0.0

# ============================================================================ 
# Load Models
# ============================================================================
model_path_best = os.path.abspath(os.path.join(current_dir, "..", "yolo", "best.pt"))
model_path_box = os.path.abspath(os.path.join(current_dir, "..", "yolo", "box.pt"))
model_path_pose = os.path.abspath(os.path.join(current_dir, "..", "yolo", "yolov8s-pose.pt"))
fire_model_path = os.path.abspath(os.path.join(current_dir, "..", "yolo", "FireNet.h5"))

detector_best = YOLODetector(model_path_best)
detector_box = YOLODetector(model_path_box)
pose_detector = YOLO(model_path_pose)
fire_detector = FireNetDetector(fire_model_path)

# ============================================================================ 
# Redis
# ============================================================================
try:
    r = redis.StrictRedis(host="localhost", port=6379, db=0, socket_timeout=5)
    r.ping()
    logger.info("✅ Redis connecté")
except redis.ConnectionError:
    logger.error("❌ Impossible de se connecter à Redis")
    raise

# ============================================================================ 
# Helpers
# ============================================================================
def decode_frame_from_redis(encoded_frame: bytes) -> Optional[np.ndarray]:
    try:
        img_data = base64.b64decode(encoded_frame + b"=" * (-len(encoded_frame) % 4))
        np_arr = np.frombuffer(img_data, np.uint8)
        return cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    except Exception as e:
        logger.error(f"❌ Frame decode error: {e}")
        return None

_last_sent_frame_hash = {}

def send_ws_frame(camera_id: int, frame: np.ndarray):
    global _last_sent_frame_hash
    try:
        _, buffer = cv2.imencode(".jpg", frame)
        frame_bytes = buffer.tobytes()
        frame_hash = hashlib.md5(frame_bytes).hexdigest()
        last_hash, last_time = _last_sent_frame_hash.get(camera_id, (None, 0))
        now = time.time()
        if frame_hash != last_hash or now - last_time >= 1.0:
            frame_b64 = base64.b64encode(frame_bytes).decode("utf-8")
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                "camera_streams",
                {"type": "send_frame", "camera_id": camera_id, "frame": frame_b64, "timestamp": timezone.now().isoformat()}
            )
            _last_sent_frame_hash[camera_id] = (frame_hash, now)
            logger.debug(f"📤 WS frame sent cam {camera_id}")
    except Exception as e:
        logger.error(f"❌ WebSocket error: {e}")

def process_detections(frame, detections, camera_id, run_ocr=False):
    annotated = frame.copy()
    for det in detections:
        x1, y1, x2, y2 = det["bbox"]
        label = f"{det['class_name']} {det['confidence']:.2f}"
        cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(annotated, label, (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        if run_ocr and det["class_name"] == "plate":
            roi = frame[y1:y2, x1:x2]
            run_ocr_task.delay(camera_id, roi.tolist())
    return annotated

def classify_pose(result, frame_height):
    persons = []
    try:
        if result.keypoints is not None:
            for kp in result.keypoints:
                kps = kp.xy.cpu().numpy()
                y_coords = kps[:, 1]
                if np.std(y_coords) < 20:
                    label = "Fallen"
                elif np.max(y_coords) - np.min(y_coords) > frame_height * 0.8:
                    label = "Aggression"
                else:
                    label = "Normal"
                persons.append((label, kps))
    except Exception as e:
        logger.error(f"❌ classify_pose error: {e}")
    return persons

# ============================================================================ 
# Main Detection Task
# ============================================================================
@shared_task
def detect_from_redis(camera_id: int, max_iterations: int = 1000):
    logger.info(f"🚀 Start detection cam {camera_id}")
    iterations = 0
    consecutive_errors = 0
    max_consecutive_errors = 10
    try:
        while iterations < max_iterations:
            encoded_frame = r.get(f"camera:{camera_id}:frame")  # ✅ Correct key
            if not encoded_frame:
                logger.warning(f"[{camera_id}] No frame found in Redis")
                time.sleep(0.5)
                continue

            frame = decode_frame_from_redis(encoded_frame)
            if frame is None:
                consecutive_errors += 1
                if consecutive_errors > max_consecutive_errors:
                    logger.error(f"[{camera_id}] Too many decode errors, stopping")
                    break
                time.sleep(0.2)
                continue
            consecutive_errors = 0
            frame = cv2.resize(frame, (640, 384))
            annotated_frame = frame.copy()

            # --- YOLO best ---
            detections_best, _ = detector_best.detect(frame)
            if detections_best:
                annotated_frame = process_detections(annotated_frame, detections_best, camera_id, run_ocr=True)

            # --- YOLO box ---
            detections_box, _ = detector_box.detect(frame)
            if detections_box:
                annotated_frame = process_detections(annotated_frame, detections_box, camera_id, run_ocr=False)

            # --- FireNet ---
            fire_prob = fire_detector.predict_fire(frame)
            if fire_prob > 0.5:
                logger.info(f"🔥 Fire prob {fire_prob:.2f} cam {camera_id}")

            # --- Pose ---
            pose_results = pose_detector.predict(
                source=frame,
                conf=0.5,
                device="cuda" if torch.cuda.is_available() else "cpu",
                verbose=False
            )
            persons = classify_pose(pose_results[0], frame.shape[0])
            for label, _ in persons:
                if label in ("Fallen", "Aggression"):
                    logger.info(f"⚠️ Pose {label} detected cam {camera_id}")

            # --- Send frame ---
            send_ws_frame(camera_id, annotated_frame)

            torch.cuda.empty_cache()
            gc.collect()
            time.sleep(0.1)  # small sleep to limit loop speed
            iterations += 1

    except Exception as e:
        logger.error(f"❌ Main loop error: {e}")
    finally:
        logger.info(f"🧹 End detection cam {camera_id}")
        return {"camera_id": camera_id, "iterations_completed": iterations, "status": "completed"}
