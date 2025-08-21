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


@shared_task(name="gismap.streaming_tasks.stream_rtsp_camera")
def stream_camera(camera_id, rtsp_url, fps=1):
    print(f"[{camera_id}] FFmpeg streaming started")

    # FFmpeg command: decode RTSP and output raw frames in BGR24
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
        stderr=subprocess.PIPE,  # capture logs for debugging
        bufsize=10**8
    )

    width, height = 1280, 720  # fallback if we cannot read actual size
    frame_size = width * height * 3  # BGR24

    try:
        while True:
            raw_frame = process.stdout.read(frame_size)
            if len(raw_frame) != frame_size:
                # Read FFmpeg stderr for info
                err = process.stderr.read(1024).decode('utf-8', errors='ignore')
                print(f"[{camera_id}] Frame incomplete ({len(raw_frame)} bytes), retrying...")
                if err:
                    print(f"[{camera_id}] FFmpeg stderr: {err.strip()}")
                time.sleep(1)
                continue

            # Convert raw bytes → numpy array
            frame = np.frombuffer(raw_frame, np.uint8).reshape((height, width, 3))

            # Encode JPEG
            ret, buffer = cv2.imencode(".jpg", frame)
            if not ret:
                print(f"[{camera_id}] JPEG encoding failed")
                continue

            # Encode to base64 for Redis
            jpg_base64 = base64.b64encode(buffer).decode("utf-8")
            redis_client.set(f"camera_frame_{camera_id}", jpg_base64, ex=5)

            print(f"[{camera_id}] Frame pushed to Redis")

    except Exception as e:
        print(f"[{camera_id}] Error in FFmpeg stream: {e}")
    finally:
        process.kill()
        print(f"[{camera_id}] FFmpeg stream ended")


@shared_task(name="gismap.tasks.streaming_tasks.stream_all_cameras")
def stream_all_cameras():
    cameras = Camera.objects.all()
    for camera in cameras:
        if should_start_stream(camera.id):
            print(f"Starting FFmpeg stream for camera {camera.id}")
            stream_camera.delay(camera.id, camera.rtsp_url)


@shared_task(name="gismap.tasks.streaming_tasks.detect_all_cameras")
def detect_all_cameras():
    from gismap.models import Camera
    cameras = Camera.objects.all()
    for camera in cameras:
        detect_from_redis.delay(camera.id)
