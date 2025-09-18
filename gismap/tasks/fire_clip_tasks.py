import cv2
import numpy as np
import torch
import redis
import time
import gc
import logging
import json
from ultralytics import YOLO
from celery import shared_task
import clip
from PIL import Image

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Redis client
r = redis.StrictRedis(host="localhost", port=6379, db=0, socket_timeout=5)

# Device (GPU si disponible)
device = "cuda" if torch.cuda.is_available() else "cpu"

# Charger modèle YOLO Fire (modèle entraîné)
model_fire = YOLO("gismap/yolo/best (1).pt").to(device)

# Charger modèle CLIP
clip_model, clip_preprocess = clip.load("ViT-B/32", device=device)


def generate_clip_description(frame: np.ndarray) -> str:
    """
    Génère une description avec CLIP sur l'image passée.
    Retourne le prompt le plus probable avec sa confiance.
    """
    try:
        image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        image_input = clip_preprocess(image).unsqueeze(0).to(device)

        prompts = [
            "A photo showing fire",
            "Smoke and fire are visible",
            "Flames and smoke in the image",
            "A photo of burning fire",
            "No fire in the image",
            "No flames or smoke"
        ]
        text_tokens = clip.tokenize(prompts).to(device)

        with torch.no_grad():
            image_features = clip_model.encode_image(image_input)
            text_features = clip_model.encode_text(text_tokens)
            similarities = (image_features @ text_features.T).softmax(dim=-1)

            best_idx = similarities.argmax().item()
            confidence = similarities[0, best_idx].item()

            return f"{prompts[best_idx]} (confidence={confidence:.2f})"

    except Exception as e:
        logger.error(f"❌ CLIP description error: {e}")
        return "Description unavailable"


@shared_task
def detect_fire_from_redis(camera_id: int, max_iterations: int = 5, conf_threshold: float = 0.25):
    from gismap.tasks.notification_tasks import send_fire_alert

    logger.info(f"🔥 Start fire detection for camera {camera_id}")
    iterations = 0

    try:
        while iterations < max_iterations:
            jpeg_bytes = r.get(f"camera:{camera_id}:frame")
            if not jpeg_bytes:
                logger.debug(f"[{camera_id}] No frame found in Redis, waiting...")
                time.sleep(0.5)
                continue

            np_arr = np.frombuffer(jpeg_bytes, np.uint8)
            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            if frame is None:
                logger.warning(f"[{camera_id}] Failed to decode frame")
                time.sleep(0.2)
                continue

            frame = cv2.resize(frame, (640, 384))
            logger.info(f"[{camera_id}] Frame shape: {frame.shape}, dtype: {frame.dtype}")

            # YOLO prediction
            detections = model_fire.predict(source=frame, conf=conf_threshold, device=device, verbose=True)
            fire_detected = False
            clip_descriptions = []
            annotated = frame.copy()

            h, w, _ = frame.shape
            pad = 10  # Padding autour des boxes YOLO pour CLIP

            for result in detections:
                if result.boxes is not None and len(result.boxes) > 0:
                    for box in result.boxes:
                        x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                        conf = float(box.conf[0])
                        cls_id = int(box.cls[0])
                        cls_name = model_fire.names[cls_id]

                        # Dessiner boîte
                        color = (0, 0, 255) if cls_name.lower() == "fire" else (255, 255, 0)
                        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
                        cv2.putText(annotated, f"{cls_name} {conf:.2f}", (x1, y1 - 5),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

                        if cls_name.lower() == "fire":
                            fire_detected = True
                            # Crop YOLO avec padding
                            x1_pad = max(x1 - pad, 0)
                            y1_pad = max(y1 - pad, 0)
                            x2_pad = min(x2 + pad, w)
                            y2_pad = min(y2 + pad, h)
                            fire_crop = frame[y1_pad:y2_pad, x1_pad:x2_pad]
                            description = generate_clip_description(fire_crop)
                            clip_descriptions.append(description)
                            logger.info(f"[{camera_id}] CLIP description (crop): {description}")

            # Si aucun feu détecté par YOLO, CLIP sur l'image entière
            if not fire_detected:
                description = generate_clip_description(frame)
                clip_descriptions.append(description)
                logger.info(f"[{camera_id}] CLIP description (full image): {description}")

            # 🔔 Envoyer alerte si feu détecté
            if fire_detected:
                send_fire_alert.delay(
                    camera_id=camera_id,
                    camera_name=f"Caméra {camera_id}",
                    details={"clip_descriptions": clip_descriptions}
                )
                logger.info(f"[{camera_id}] 🔔 Fire alert sent")

            # Stocker dans Redis
            _, buffer = cv2.imencode(".jpg", annotated)
            r.set(f"frame:{camera_id}:fire", buffer.tobytes(), ex=5)

            result_data = {
                "fire_detected": fire_detected,
                "clip_descriptions": clip_descriptions
            }
            r.set(f"result:{camera_id}:fire", json.dumps(result_data), ex=10)

            logger.info(f"[{camera_id}] 🔥 Fire detected={fire_detected}, CLIP='{clip_descriptions}'")

            torch.cuda.empty_cache()
            gc.collect()
            iterations += 1
            time.sleep(0.2)

    except Exception as e:
        logger.error(f"[{camera_id}] Fire detection error: {e}")

    finally:
        logger.info(f"🧹 End fire detection for camera {camera_id}, iterations={iterations}")
        return {"camera_id": camera_id, "iterations": iterations}
