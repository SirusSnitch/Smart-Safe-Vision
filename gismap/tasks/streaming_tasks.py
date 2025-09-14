import redis
from celery import shared_task
import subprocess
import time
import numpy as np
import cv2
from gismap.models import Camera
from gismap.tasks.yolo_detect_task import detect_from_redis

# Redis client
redis_client = redis.StrictRedis(host='localhost', port=6379, db=0)

@shared_task(name="gismap.streaming_tasks.stream_rtsp_camera")
def stream_camera(camera_id, rtsp_url, width=640, height=480, fps=1):
    redis_key = f"camera:{camera_id}:streaming"

    if redis_client.get(redis_key):
        print(f"[{camera_id}] Already streaming according to Redis, skipping")
        return
    redis_client.set(redis_key, "1")

    print(f"[{camera_id}] FFmpeg streaming started for {rtsp_url}")

    ffmpeg_cmd = [
        "ffmpeg",
        "-rtsp_transport", "tcp",
        "-i", rtsp_url,
        "-map", "0:v:0",
        "-an",
        "-s", f"{width}x{height}",
        "-vf", f"fps={fps}",
        "-f", "rawvideo",
        "-pix_fmt", "bgr24",
        "pipe:1"
    ]

    process = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=10**8)
    frame_size = width * height * 3
    detection_started = False
    iteration = 0

    try:
        while True:
            iteration += 1
            raw_frame = process.stdout.read(frame_size)

            if not raw_frame or len(raw_frame) < frame_size:
                err = process.stderr.read(4096).decode("utf-8", errors="ignore")
                print(f"[{camera_id}] Incomplete frame ({len(raw_frame)} bytes)")
                if err.strip():
                    print(f"[{camera_id}] FFmpeg error: {err.strip()}")
                time.sleep(0.5)
                continue

            try:
                frame = np.frombuffer(raw_frame, np.uint8).reshape((height, width, 3))
            except ValueError:
                print(f"[{camera_id}] Failed to reshape frame buffer")
                continue

            ret, buffer = cv2.imencode(".jpg", frame)
            if ret:
                redis_client.set(f"camera:{camera_id}:frame", buffer.tobytes(), ex=5)
                print(f"[{camera_id}] Iteration {iteration}: frame decoded successfully")
                print(f"[{camera_id}] ✅ Frame pushed to Redis")

            if not detection_started:
                detect_from_redis.delay(camera_id)
                detection_started = True
                print(f"[{camera_id}] YOLO detection started")

    except Exception as e:
        print(f"[{camera_id}] Exception: {e}")
    finally:
        process.kill()
        redis_client.delete(redis_key)
        print(f"[{camera_id}] FFmpeg stream ended")
