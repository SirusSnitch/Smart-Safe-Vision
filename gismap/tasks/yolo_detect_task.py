
# ============================================================================
# YOLO_DETECT_TASK.PY - Version optimisée
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
from typing import Optional, Tuple
from gismap.tasks.ocr_task import run_ocr_task

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class YOLODetector:
    """Classe pour gérer le modèle YOLO de manière optimisée"""
    
    def __init__(self, model_path: str):
        self.model_path = model_path
        self.model = None
        self.load_model()
    
    def load_model(self):
        """Chargement sécurisé du modèle"""
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
        """Détection des plaques avec gestion d'erreurs"""
        try:
            results = self.model.predict(
                source=frame,
                save=False,
                conf=conf_threshold,
                device='cuda',
                imgsz=(640, 384),
                verbose=False  # Réduire les logs YOLO
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

# Initialisation du détecteur
current_dir = os.path.dirname(__file__)
model_path = os.path.abspath(os.path.join(current_dir, "..", "yolo", "best.pt"))
detector = YOLODetector(model_path)

# Connexion Redis avec gestion d'erreurs
try:
    r = redis.StrictRedis(host='localhost', port=6379, db=0, socket_timeout=5)
    r.ping()  # Test de connexion
    logger.info("✅ Connexion Redis établie")
except redis.ConnectionError:
    logger.error("❌ Impossible de se connecter à Redis")
    raise

def decode_frame_from_redis(encoded_frame: bytes) -> Optional[np.ndarray]:
    """Décodage sécurisé des frames depuis Redis"""
    try:
        # Corriger le padding base64
        img_data = base64.b64decode(encoded_frame + b'=' * (-len(encoded_frame) % 4))
        np_arr = np.frombuffer(img_data, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        
        if frame is None:
            logger.warning("Image vide après décodage")
            return None
            
        return frame
        
    except Exception as e:
        logger.error(f"Erreur décodage frame: {e}")
        return None

def process_detections(frame: np.ndarray, detections: list, camera_id: int) -> np.ndarray:
    """Traitement des détections et envoi vers OCR"""
    annotated_frame = frame.copy()
    
    for detection in detections:
        x1, y1, x2, y2 = detection['bbox']
        confidence = detection['confidence']
        
        # Validation de la taille de la détection
        width, height = x2 - x1, y2 - y1
        if width < 50 or height < 20:  # Trop petite
            continue
            
        # Extraction de la région d'intérêt avec marge
        margin = 5
        x1_crop = max(0, x1 - margin)
        y1_crop = max(0, y1 - margin)
        x2_crop = min(frame.shape[1], x2 + margin)
        y2_crop = min(frame.shape[0], y2 + margin)
        
        cropped = frame[y1_crop:y2_crop, x1_crop:x2_crop]
        
        if cropped.size > 0:
            # Encoder la plaque en bytes pour la task OCR
            _, buffer = cv2.imencode('.jpg', cropped, [cv2.IMWRITE_JPEG_QUALITY, 95])
            image_bytes = buffer.tobytes()
            
            logger.info(f"📤 Envoi détection à OCR (Cam {camera_id}, conf: {confidence:.2f})")
            
            # Appel asynchrone à la task OCR
            run_ocr_task.delay(image_bytes, camera_id)
        
        # Annotation de la frame
        cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(annotated_frame, f'{confidence:.2f}', (x1, y1-10), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    
    return annotated_frame

@shared_task
def detect_from_redis(camera_id: int, max_iterations: int = 1000):
    """
    Task de détection optimisée avec gestion d'erreurs et limitations
    """
    logger.info(f"🚀 Démarrage détection YOLO pour caméra {camera_id}")
    
    iterations = 0
    consecutive_errors = 0
    max_consecutive_errors = 10
    
    try:
        while iterations < max_iterations:
            try:
                # Récupération de la frame depuis Redis
                encoded_frame = r.get(f"camera_frame_{camera_id}")
                
                if not encoded_frame:
                    logger.debug(f"⏳ En attente de frame pour caméra {camera_id}")
                    time.sleep(0.5)  # Réduction du délai
                    continue
                
                # Décodage de la frame
                frame = decode_frame_from_redis(encoded_frame)
                if frame is None:
                    consecutive_errors += 1
                    if consecutive_errors > max_consecutive_errors:
                        logger.error(f"Trop d'erreurs consécutives, arrêt de la caméra {camera_id}")
                        break
                    continue
                
                # Reset du compteur d'erreurs
                consecutive_errors = 0
                
                # Redimensionnement optimal
                frame = cv2.resize(frame, (640, 384))
                
                # Détection des plaques
                detections, yolo_results = detector.detect_plates(frame)
                
                if detections:
                    logger.info(f"🎯 {len(detections)} plaque(s) détectée(s) (Cam {camera_id})")
                    
                    # Traitement des détections
                    annotated_frame = process_detections(frame, detections, camera_id)
                else:
                    annotated_frame = frame
                
                # Affichage (optionnel - peut être désactivé en production)
                if os.getenv('ENABLE_DISPLAY', 'true').lower() == 'true':
                    cv2.imshow(f"🎯 Caméra {camera_id}", annotated_frame)
                    
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        logger.info(f"🛑 Arrêt demandé par utilisateur")
                        break
                
                # Nettoyage mémoire
                if yolo_results:
                    del yolo_results
                torch.cuda.empty_cache()
                gc.collect()
                
                # Délai adaptatif
                time.sleep(0.1)
                iterations += 1
                
            except redis.ConnectionError:
                logger.error(f"❌ Perte de connexion Redis")
                time.sleep(5)  # Attendre avant de reconnecter
                consecutive_errors += 1
                
            except Exception as e:
                logger.error(f"❌ Erreur dans la boucle de détection: {e}")
                consecutive_errors += 1
                time.sleep(1)
                
                if consecutive_errors > max_consecutive_errors:
                    logger.error(f"Arrêt après {max_consecutive_errors} erreurs consécutives")
                    break
    
    except KeyboardInterrupt:
        logger.info("🛑 Interruption clavier détectée")
    
    except Exception as e:
        logger.error(f"❌ Erreur fatale: {e}")
    
    finally:
        cv2.destroyAllWindows()
        logger.info(f"🧹 Nettoyage terminé pour caméra {camera_id}")
        
        return {
            "camera_id": camera_id,
            "iterations_completed": iterations,
            "status": "completed"
        }

# ============================================================================
# FONCTIONS UTILITAIRES SUPPLÉMENTAIRES
# ============================================================================

@shared_task
def cleanup_debug_files(max_age_hours: int = 24):
    """Task de nettoyage des fichiers debug anciens"""
    try:
        current_time = time.time()
        deleted_count = 0
        
        for filename in os.listdir(debug_dir):
            file_path = os.path.join(debug_dir, filename)
            file_age = current_time - os.path.getctime(file_path)
            
            if file_age > (max_age_hours * 3600):  # Convertir heures en secondes
                os.remove(file_path)
                deleted_count += 1
        
        logger.info(f"🧹 Nettoyage: {deleted_count} fichiers supprimés")
        return {"deleted_count": deleted_count}
        
    except Exception as e:
        logger.error(f"Erreur nettoyage: {e}")
        return {"error": str(e)}

@shared_task
def health_check_cameras():
    """Vérification de l'état des caméras dans Redis"""
    try:
        camera_status = {}
        
        # Vérifier les clés de caméras actives
        camera_keys = r.keys("camera_frame_*")
        
        for key in camera_keys:
            camera_id = key.decode().split('_')[-1]
            last_update = r.ttl(key)
            
            camera_status[camera_id] = {
                "active": last_update > 0,
                "ttl": last_update
            }
        
        logger.info(f"📊 État des caméras: {camera_status}")
        return {"camera_status": camera_status}
        
    except Exception as e:
        logger.error(f"Erreur health check: {e}")
        return {"error": str(e)}