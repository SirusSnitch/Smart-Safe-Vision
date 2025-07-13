from celery import shared_task
import cv2
import os
from datetime import datetime
from .models import Camera

@shared_task
def capture_frame(camera_id, rtsp_url):
    print(f"[{camera_id}] Capture frame")

    cap = cv2.VideoCapture(rtsp_url)
    if not cap.isOpened():
        print(f"[{camera_id}] Impossible d'ouvrir le flux RTSP")
        return

    ret, frame = cap.read()
    if not ret:
        print(f"[{camera_id}] Frame non reçue")
        cap.release()
        return

    camera_dir = f"media/captures/camera_{camera_id}"
    os.makedirs(camera_dir, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"{camera_dir}/frame_{timestamp}.jpg"
    cv2.imwrite(filename, frame)
    print(f"[{camera_id}] Image enregistrée: {filename}")

    cap.release()


@shared_task
def capture_all_cameras_once():
    cameras = Camera.objects.all()
    for camera in cameras:
        camera_id = camera.id
        rtsp_url = camera.rtsp_url
        # Tu peux aussi utiliser camera.name si besoin
        capture_frame.delay(camera_id, rtsp_url)