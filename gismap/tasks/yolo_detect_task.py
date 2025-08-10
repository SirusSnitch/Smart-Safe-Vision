# Dans votre yolo_detect_task.py, supprimez les fonctions send_unauthorized_notification 
# et check_and_save_detection et remplacez par ceci :

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
from django.apps import apps
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
        if not torch.cuda.is_available():
            raise RuntimeError("🚫 CUDA n'est pas disponible.")
        if not os.path.exists(self.model_path):
            raise FileNotFoundError(f"Modèle non trouvé: {self.model_path}")
        try:
            self.model = YOLO(self.model_path).to("cuda")
            logger.info(f"✅ Modèle YOLO chargé: {self.model_path}")
        except Exception as e:
            logger.error(f"❌ Erreur chargement modèle: {e}")
            raise

    def detect_plates(self, frame: np.ndarray, conf_threshold: float = 0.25) -> list:
        try:
            results = self.model.predict(
                source=frame,
                save=False,
                conf=conf_threshold,
                device='cuda',
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

# SUPPRIMEZ les fonctions send_unauthorized_notification et check_and_save_detection
# Elles sont maintenant gérées dans ocr_task.py via NotificationService

def process_detections(frame: np.ndarray, detections: list, camera_id: int) -> np.ndarray:
    """
    Traite les détections YOLO et lance l'OCR.
    Les notifications sont gérées automatiquement par ocr_task.py
    """
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
            
            # Lancer l'OCR - les notifications sont gérées automatiquement dans ocr_task.py
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