import base64
import cv2
import numpy as np
import torch
from ultralytics import YOLO
from celery import shared_task
import redis
import time

# Vérifier si CUDA est dispo sinon quitter
if not torch.cuda.is_available():
    raise RuntimeError("🚫 CUDA n'est pas disponible. Assurez-vous que votre carte NVIDIA est bien installée et que PyTorch a le support CUDA.")

# Charger YOLO sur le GPU
model = YOLO("yolov8n.pt").to("cuda")  # Obliger GPU

# Connexion Redis
r = redis.StrictRedis(host='localhost', port=6379, db=0)

@shared_task
def detect_from_redis(camera_id):
    print(f"[YOLO] 🚀 Démarrage détection sur GPU pour caméra {camera_id}")

    while True:
        try:
            # Lire l'image base64 depuis Redis
            encoded_frame = r.get(f"camera_frame_{camera_id}")
            if not encoded_frame:
                print(f"[YOLO] ⏳ En attente de frame pour caméra {camera_id}")
                time.sleep(1)
                continue

            try:
                img_data = base64.b64decode(encoded_frame + b'=' * (-len(encoded_frame) % 4))
                np_arr = np.frombuffer(img_data, np.uint8)
                frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            except Exception as e:
                print(f"[YOLO] ❌ Erreur décodage frame : {e}")
                continue

            if frame is None:
                print("[YOLO] ⚠️ Image vide après décodage.")
                continue

            # Détection avec GPU
            results = model.predict(
                source=frame,
                save=False,
                imgsz=(640, 384),
                conf=0.25,
                device='cuda'  # Force GPU
            )

            # Affichage
            annotated_frame = results[0].plot()
            cv2.imshow(f"🎯 Détection GPU - Caméra {camera_id}", annotated_frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                cv2.destroyAllWindows()
                break

        except Exception as e:
            print(f"[YOLO] ❌ Erreur générale : {e}")
            break
