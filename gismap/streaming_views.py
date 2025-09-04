from django.shortcuts import render
from django.http import StreamingHttpResponse
from .models import Camera, Lieu
from .streaming_utils import should_start_stream
from .tasks.streaming_tasks import stream_camera
import redis
import base64
import time

redis_client = redis.StrictRedis(host='localhost', port=6379, db=0)

import binascii

def add_base64_padding(s):
    return s + '=' * (-len(s) % 4)

def stream_camera_view(request, camera_id):
    def generate():
        while True:
            frame_data = redis_client.get(f"camera:{camera_id}:frame")
            if frame_data:
                try:
                    frame_str = frame_data.decode('utf-8').strip()
                    frame_str = add_base64_padding(frame_str)
                    jpg_bytes = base64.b64decode(frame_str)
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + jpg_bytes + b'\r\n')
                except (binascii.Error, UnicodeDecodeError) as e:
                    print(f"[STREAMING] base64 decode error: {e}")
                    time.sleep(0.1)
            else:
                time.sleep(0.1)

    return StreamingHttpResponse(generate(), content_type='multipart/x-mixed-replace; boundary=frame')

# Vue qui affiche toutes les caméras d’un département (ou toutes)
def all_cameras_stream(request):
    departement_id = request.GET.get('departement_id')
    departements = Lieu.objects.all()

    if departement_id:
        cameras = Camera.objects.filter(department_id=departement_id)
    else:
        cameras = Camera.objects.all()

    for camera in cameras:
        if should_start_stream(camera.id):
            stream_camera.delay(camera.id, camera.rtsp_url)

    context = {
        'cameras': cameras,
        'departements': departements,
        'selected_departement_id': departement_id,
    }
    return render(request, 'all_cameras.html', context)