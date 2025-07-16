from django.shortcuts import render
from django.http import StreamingHttpResponse
from .models import Camera, Lieu
from .streaming_utils import should_start_stream
from .streaming_tasks import stream_camera
import redis
import base64
import time

redis_client = redis.StrictRedis(host='localhost', port=6379, db=0)

# Vue qui génère le flux MJPEG à partir de Redis
def stream_camera_view(request, camera_id):
    def generate():
        while True:
            frame_data = redis_client.get(f"camera_frame_{camera_id}")
            if frame_data:
                jpg_bytes = base64.b64decode(frame_data)
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + jpg_bytes + b'\r\n')
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
