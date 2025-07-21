import base64
import cv2
import numpy as np
import torch
from ultralytics import YOLO
from celery import shared_task
import redis
import time
import gc  # Garbage collector

# Vérifier CUDA
if not torch.cuda.is_available():
    raise RuntimeError("🚫 CUDA n'est pas disponible.")

# Charger le modèle YOLOv8 nano sur GPU
model = YOLO("yolov8n.pt").to("cuda")

# Connexion Redis
r = redis.StrictRedis(host='localhost', port=6379, db=0)

@shared_task
def detect_from_redis(camera_id):
    print(f"[YOLO] 🚀 Démarrage détection sur GPU pour caméra {camera_id}")

    try:
        while True:
            encoded_frame = r.get(f"camera_frame_{camera_id}")
            if not encoded_frame:
                print(f"[YOLO] ⏳ En attente de frame pour caméra {camera_id}")
                time.sleep(0.5)
                continue

            try:
                # Corriger le padding base64
                img_data = base64.b64decode(encoded_frame + b'=' * (-len(encoded_frame) % 4))
                np_arr = np.frombuffer(img_data, np.uint8)
                frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

                if frame is None:
                    print("[YOLO] ⚠️ Image vide après décodage.")
                    continue

                # Redimensionnement (optionnel pour économiser mémoire)
                frame = cv2.resize(frame, (640, 384))

                # Détection
                results = model.predict(
                    source=frame,
                    save=False,
                    conf=0.25,
                    device='cuda',
                    imgsz=(640, 384)
                )

                # Affichage
                annotated_frame = results[0].plot()
                cv2.imshow(f"🎯 Caméra {camera_id}", annotated_frame)

                # Libération mémoire GPU
                del results
                torch.cuda.empty_cache()
                gc.collect()

                if cv2.waitKey(1) & 0xFF == ord('q'):
                    print(f"[YOLO] 🛑 Arrêt demandé par utilisateur (q)")
                    break

            except Exception as e:
                print(f"[YOLO] ❌ Erreur décodage ou détection : {e}")
                continue

    except Exception as e:
        print(f"[YOLO] ❌ Erreur principale : {e}")

    finally:
        cv2.destroyAllWindows()
        print(f"[YOLO] 🧹 Fenêtres fermées pour caméra {camera_id}")
