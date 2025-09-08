# ============================================================================
# YOLO_DETECT_TASK.PY - Multi-model detection, OCR only on best.pt detections
# WebSocket streaming at ~1 FPS, duplicate frames skipped
# ============================================================================
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
            raise FileNotFoundError(f"Model not found: {self.model_path}")
        device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = YOLO(self.model_path).to(device)
        logger.info(f"✅ YOLO loaded on {device.upper()}: {self.model_path}")

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
# Load Models
# ============================================================================
model_path_best = os.path.abspath(os.path.join(current_dir, "..", "yolo", "best.pt"))
model_path_box = os.path.abspath(os.path.join(current_dir, "..", "yolo", "box.pt"))
model_path_pose = os.path.abspath(os.path.join(current_dir, "..", "yolo", "yolov8s-pose.pt"))

detector_best = YOLODetector(model_path_best)
detector_box = YOLODetector(model_path_box)
pose_detector = YOLO(model_path_pose)

# ============================================================================
# Redis
# ============================================================================
try:
    r = redis.StrictRedis(host="localhost", port=6379, db=0, socket_timeout=5)
    r.ping()
    logger.info("✅ Redis connected")
except redis.ConnectionError:
    logger.error("❌ Cannot connect to Redis")
    raise

# ============================================================================
# Helpers
# ============================================================================
def decode_frame_from_redis(jpeg_bytes: bytes) -> Optional[np.ndarray]:
    """Decode raw JPEG bytes (not base64) from Redis into a cv2 frame."""
    try:
        np_arr = np.frombuffer(jpeg_bytes, np.uint8)
        return cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    except Exception as e:
        logger.error(f"❌ Frame decode error: {e}")
        return None

_last_sent_frame_hash = {}

def send_ws_frame(camera_id: int, frame: np.ndarray):
    """Send frame over WebSocket, avoid duplicates, enforce ~1 FPS."""
    global _last_sent_frame_hash
    try:
        _, buffer = cv2.imencode(".jpg", frame)
        frame_bytes = buffer.tobytes()
        frame_hash = hashlib.md5(frame_bytes).hexdigest()

        last_hash, last_time = _last_sent_frame_hash.get(camera_id, (None, 0))
        now = time.time()

        if frame_hash != last_hash or now - last_time >= 1.0:
            # Still base64 for WebSocket JSON transport
            import base64
            frame_b64 = base64.b64encode(frame_bytes).decode("utf-8")

            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                "camera_streams",
                {
                    "type": "send_frame",
                    "camera_id": camera_id,
                    "frame": frame_b64,
                    "timestamp": timezone.now().isoformat()
                }
            )
            _last_sent_frame_hash[camera_id] = (frame_hash, now)
            logger.debug(f"📤 WS frame sent cam {camera_id}")
    except Exception as e:
        logger.error(f"❌ WebSocket error: {e}")

def process_detections(frame, detections, camera_id, run_ocr=False):
    """Draw bounding boxes and optionally run OCR on plates."""
    annotated = frame.copy()
    for det in detections:
        x1, y1, x2, y2 = det["bbox"]
        label = f"{det['class_name']} {det['confidence']:.2f}"
        cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(annotated, label, (x1, y1 - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        if run_ocr and det["class_name"] == "plate":
            roi = frame[y1:y2, x1:x2]
            run_ocr_task.delay(camera_id, roi.tolist())
    return annotated

def classify_pose(result, frame_height):
    """Classify person pose into Fallen / Aggression / Normal."""
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
            jpeg_bytes = r.get(f"camera:{camera_id}:frame")
            if not jpeg_bytes:
                logger.warning(f"[{camera_id}] No frame found in Redis")
                time.sleep(0.5)
                continue

            frame = decode_frame_from_redis(jpeg_bytes)
            if frame is None:
                consecutive_errors += 1
                logger.warning(f"[{camera_id}] Frame decode failed, consecutive errors: {consecutive_errors}")
                if consecutive_errors > max_consecutive_errors:
                    logger.error(f"[{camera_id}] Too many decode errors, stopping detection")
                    break
                time.sleep(0.2)
                continue

            consecutive_errors = 0
            frame = cv2.resize(frame, (640, 384))
            annotated_frame = frame.copy()

            logger.info(f"[{camera_id}] Iteration {iterations+1}: frame decoded successfully")

            # --- YOLO best ---
            detections_best, _ = detector_best.detect(frame)
            logger.info(f"[{camera_id}] YOLO best detections: {len(detections_best)}")
            if detections_best:
                annotated_frame = process_detections(annotated_frame, detections_best, camera_id, run_ocr=True)

            # --- YOLO box ---
            detections_box, _ = detector_box.detect(frame)
            logger.info(f"[{camera_id}] YOLO box detections: {len(detections_box)}")
            if detections_box:
                annotated_frame = process_detections(annotated_frame, detections_box, camera_id, run_ocr=False)

            # --- Pose ---
            pose_results = pose_detector.predict(
                source=frame,
                conf=0.5,
                device="cuda" if torch.cuda.is_available() else "cpu",
                verbose=False
            )
            persons = classify_pose(pose_results[0], frame.shape[0])
            for label, _ in persons:
                logger.info(f"[{camera_id}] Pose detected: {label}")
            if not persons:
                logger.info(f"[{camera_id}] No persons detected in this frame")

            # --- Send frame ---
            send_ws_frame(camera_id, annotated_frame)

            torch.cuda.empty_cache()
            gc.collect()
            time.sleep(0.1)
            iterations += 1

    except Exception as e:
        logger.error(f"[{camera_id}] Main detection loop error: {e}")
    finally:
        logger.info(f"🧹 End detection cam {camera_id}, iterations completed: {iterations}")
        return {"camera_id": camera_id, "iterations_completed": iterations, "status": "completed"}
