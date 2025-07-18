from celery import shared_task
import cv2
import redis
import base64
import time
from gismap.models import Camera
from gismap.streaming_utils import should_start_stream
from gismap.tasks.yolo_detect_task import detect_from_redis

redis_client = redis.StrictRedis(host='localhost', port=6379, db=0)

@shared_task(name="gismap.streaming_tasks.stream_rtsp_camera")
def stream_camera(camera_id, rtsp_url):
    print(f"[{camera_id}] Streaming démarré")
    cap = cv2.VideoCapture(rtsp_url)

    if not cap.isOpened():
        print(f"[{camera_id}] Erreur d'ouverture RTSP")
        return

    while True:
        ret, frame = cap.read()
        if not ret:
            print(f"[{camera_id}] Frame non reçue")
            break

        _, buffer = cv2.imencode('.jpg', frame)
        jpg_base64 = base64.b64encode(buffer).decode('utf-8')
        redis_client.set(f"camera_frame_{camera_id}", jpg_base64)

        time.sleep(0.03)

    cap.release()
    print(f"[{camera_id}] Fin du stream")


#from .streaming_utils import should_start_stream

@shared_task(name="gismap.tasks.streaming_tasks.stream_all_cameras")
def stream_all_cameras():
    cameras = Camera.objects.all()
    for camera in cameras:
        if should_start_stream(camera.id):  # ✅ Évite les redondances
            print(f"Lancement du stream pour caméra {camera.id}")
            stream_camera.delay(camera.id, camera.rtsp_url)
@shared_task(name="gismap.tasks.streaming_tasks.detect_all_cameras")
def detect_all_cameras():
    from gismap.models import Camera  # import déplacé ici
    cameras = Camera.objects.all()
    for camera in cameras:
        detect_from_redis.delay(camera.id)
