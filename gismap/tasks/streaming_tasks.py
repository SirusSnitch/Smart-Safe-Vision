from celery import shared_task
import subprocess
import redis
import base64
import time
import numpy as np
import cv2
from gismap.models import Camera
from gismap.streaming_utils import should_start_stream
from gismap.tasks.yolo_detect_task import detect_from_redis

redis_client = redis.StrictRedis(host='localhost', port=6379, db=0)

# Keep track of running cameras and detection tasks
running_cameras = set()
running_detections = set()


@shared_task(name="gismap.streaming_tasks.stream_rtsp_camera")
def stream_camera(camera_id, rtsp_url, fps=1):
    if camera_id in running_cameras:
        print(f"[{camera_id}] Already streaming, skipping duplicate task")
        return
    running_cameras.add(camera_id)

    print(f"[{camera_id}] FFmpeg streaming started")
    ffmpeg_cmd = [
        "ffmpeg",
        "-i", rtsp_url,
        "-f", "rawvideo",
        "-pix_fmt", "bgr24",
        "-vf", f"fps={fps}",
        "-an",
        "pipe:1"
    ]

    process = subprocess.Popen(
        ffmpeg_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=10**8
    )

    width, height = 1280, 720
    frame_size = width * height * 3
    detection_started = False

    try:
        while True:
            raw_frame = process.stdout.read(frame_size)
            if len(raw_frame) != frame_size:
                err = process.stderr.read(1024).decode('utf-8', errors='ignore')
                print(f"[{camera_id}] Frame incomplete ({len(raw_frame)} bytes), retrying...")
                if err:
                    print(f"[{camera_id}] FFmpeg stderr: {err.strip()}")
                time.sleep(1)
                continue

            frame = np.frombuffer(raw_frame, np.uint8).reshape((height, width, 3))
            ret, buffer = cv2.imencode(".jpg", frame)
            if not ret:
                print(f"[{camera_id}] JPEG encoding failed")
                continue

            jpg_base64 = base64.b64encode(buffer).decode("utf-8")
            redis_client.set(f"camera:{camera_id}:frame", jpg_base64, ex=5)
            print(f"[{camera_id}] Frame pushed to Redis")

            # Start YOLO detection once, after the first frame
            if not detection_started:
                if camera_id not in running_detections:
                    detect_from_redis.delay(camera_id)
                    running_detections.add(camera_id)
                    detection_started = True
                    print(f"[{camera_id}] YOLO detection started")

    except Exception as e:
        print(f"[{camera_id}] Error in FFmpeg stream: {e}")
    finally:
        process.kill()
        running_cameras.remove(camera_id)
        print(f"[{camera_id}] FFmpeg stream ended")
        if camera_id in running_detections:
            running_detections.remove(camera_id)


@shared_task(name="gismap.tasks.streaming_tasks.stream_all_cameras")
def stream_all_cameras():
    cameras = Camera.objects.all()
    for camera in cameras:
        if should_start_stream(camera.id):
            stream_camera.delay(camera.id, camera.rtsp_url)


@shared_task(name="gismap.tasks.streaming_tasks.detect_all_cameras")
def detect_all_cameras():
    cameras = Camera.objects.all()
    for camera in cameras:
        detect_from_redis.delay(camera.id)
