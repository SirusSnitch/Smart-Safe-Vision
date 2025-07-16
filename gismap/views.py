from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
import json
from django.contrib.gis.geos import GEOSGeometry, Point
from .models import Lieu, Camera
import os
from django.conf import settings
import traceback
from django.views.decorators.http import require_http_methods
from django.core.serializers import serialize
from django.contrib.gis.serializers import geojson  # ajoute ceci
from urllib.parse import urlparse
import subprocess
from .streaming_tasks import stream_camera


import os
import cv2
import threading
import time
from datetime import datetime

def generate_hls_url(rtsp_url):
    """Convertit une URL RTSP en HLS avec MediaMTX"""
    parsed = urlparse(rtsp_url)
    stream_name = parsed.path.split('/')[-1]  # Récupère le nom du flux (ex: 'stream1')
    return f"http://192.168.1.30:8888/{stream_name}/index.m3u8"
def process_camera_stream(camera_id, rtsp_url):
    print(f"[{camera_id}] Started processing thread for {rtsp_url}")
    cap = cv2.VideoCapture(rtsp_url)

    if not cap.isOpened():
        print(f"[{camera_id}] Échec de la connexion au flux")
        return

    camera_dir = f"media/captures/camera_{camera_id}"
    os.makedirs(camera_dir, exist_ok=True)

    last_saved = time.time()

    while True:
        ret, frame = cap.read()
        if not ret:
            print(f"[{camera_id}] Frame non reçue")
            time.sleep(1)
            continue

        now = time.time()
        if now - last_saved >= 30:  # 30 secondes
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{camera_dir}/frame_{timestamp}.jpg"
            cv2.imwrite(filename, frame)
            print(f"[{camera_id}] Image enregistrée: {filename}")
            last_saved = now

        # Limite la charge CPU
        time.sleep(0.03)


running_threads = {}
def start_camera_thread(id, url):
    if id not in running_threads:
        t = threading.Thread(target=process_camera_stream, args=(id, url), daemon=True)
        t.start()
        running_threads[id] = t
        print(f"[INFO] Thread caméra {id} lancé. Threads actifs : {threading.active_count()}")
        print(f"[DEBUG] Threads caméras en cours : {list(running_threads.keys())}")
    else:
        print(f"[INFO] Le thread pour la caméra {id} est déjà en cours.")



def index(request):
    return render(request, 'map/index.html')  # Pense à bien mettre 'map/index.html' si dans templates/map/

@csrf_exempt
@require_http_methods(["POST"])
def save_polygon(request):
    try:
        data = json.loads(request.body)
        polygon_id = data.get('id')  # ID optionnel pour update
        name = data.get('name')
        geometry = data.get('geometry')
        area = data.get('area', 0)

        if not name or not geometry:
            return JsonResponse({'error': 'Name and geometry are required'}, status=400)

        geom = GEOSGeometry(json.dumps(geometry))
        if not geom.valid:
            return JsonResponse({'error': 'Invalid geometry'}, status=400)

        if polygon_id:
            # Update existant
            lieu = Lieu.objects.get(pk=polygon_id)
            lieu.name = name
            lieu.polygon = geom
            lieu.area = float(area)
            lieu.save()
            message = 'Polygon updated successfully'
        else:
            # Création nouveau
            lieu = Lieu(name=name, polygon=geom, area=float(area))
            lieu.save()
            message = 'Polygon saved successfully'

        return JsonResponse({
            'status': 'success',
            'message': message,
            'id': lieu.id
        })

    except Lieu.DoesNotExist:
        return JsonResponse({'error': 'Polygon not found'}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e), 'traceback': traceback.format_exc()}, status=500)


@require_http_methods(["GET"])
def get_polygons(request):
    lieux = Lieu.objects.all()
    if lieux.exists():
        geojson_data = geojson.Serializer().serialize(
            lieux,
            use_natural_primary_keys=False,
            geometry_field='polygon',
            fields=('name', 'area')
        )
        geojson_dict = json.loads(geojson_data)
    else:
        geojson_dict = {"type": "FeatureCollection", "features": []}
    
    return JsonResponse(geojson_dict)


@require_http_methods(["GET"])
def get_isgb_polygon(request):
    try:
        # Ajuste ce chemin si besoin (ici 'app/static/data/isgb.geojson')
        geojson_path = os.path.join(settings.BASE_DIR, 'app', 'static', 'data', 'isgb.geojson')

        if not os.path.exists(geojson_path):
            return JsonResponse({
                'status': 'error',
                'message': 'Fichier GeoJSON introuvable',
                'path': geojson_path,
                'content': os.listdir(os.path.dirname(geojson_path)) if os.path.exists(os.path.dirname(geojson_path)) else 'Directory not found'
            }, status=404)

        with open(geojson_path, 'r', encoding='utf-8') as f:
            geojson_data = json.load(f)

        if not isinstance(geojson_data, dict):
            return JsonResponse({'status': 'error', 'message': 'Format GeoJSON invalide'}, status=400)

        return JsonResponse(geojson_data)

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e),
            'traceback': traceback.format_exc()
        }, status=500)


@csrf_exempt
@require_http_methods(["DELETE"])
def delete_polygon(request, polygon_id):
    try:
        lieu = Lieu.objects.get(pk=polygon_id)
        lieu.delete()
        return JsonResponse({'status': 'success', 'message': 'Polygon deleted successfully'})
    except Lieu.DoesNotExist:
        return JsonResponse({'error': 'Polygon not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e), 'traceback': traceback.format_exc()}, status=500)
    



@csrf_exempt
def save_camera(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            name = data.get('name')
            rtsp_url = data.get('url')
            hls_url = generate_hls_url(rtsp_url)  #
            coordinates = data.get('coordinates')  # [lng, lat]

            if not name or not hls_url or not coordinates:
                return JsonResponse({'error': 'Name, URL, and coordinates are required'}, status=400)

            point = Point(coordinates[0], coordinates[1])

            # Vérifier que la caméra est dans un lieu (polygone)
            department = None
            for lieu in Lieu.objects.all():
                if lieu.polygon.contains(point):
                    department = lieu
                    break

            if department is None:
                # Pas dans un lieu -> Refus
                return JsonResponse({
                    'status': 'error',
                    'message': "La caméra doit être placée à l'intérieur d'un département existant."
                }, status=400)

            camera = Camera.objects.create(
                name=name,
                rtsp_url=rtsp_url,
                hls_url=hls_url,
                location=point,
                department=department
            )
          #  capture_frame.delay(camera.id, rtsp_url)  # lance la tâche asynchrone Celery

            start_camera_thread(camera.id, rtsp_url)
            return JsonResponse({
                'status': 'success',
                'message': 'Camera saved successfully',
                'id': camera.id,
                'department_id': department.id
            })
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Method not allowed'}, status=405)


def get_cameras(request):
    if request.method == 'GET':
        try:
            cameras = Camera.objects.all()
            features = []
            for cam in cameras:
                features.append({
                    "type": "Feature",
                    "geometry": json.loads(cam.location.geojson),
                    "properties": {
                        "id": cam.id,
                        "name": cam.name,
                        "rtsp_url": cam.rtsp_url,
                        "department_id": cam.department.id if cam.department else None,
                        "department_name": cam.department.name if cam.department else None,
                    },
                    "id": cam.id  # For frontend deletion
                })
            return JsonResponse({
                "type": "FeatureCollection",
                "features": features
            })
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Method not allowed'}, status=405)


@csrf_exempt
@require_http_methods(["DELETE"])
def delete_camera(request, camera_id):
    try:
        camera = Camera.objects.get(pk=camera_id)
        camera.delete()
        return JsonResponse({'status': 'success', 'message': 'Camera deleted successfully'})
    except Camera.DoesNotExist:
        return JsonResponse({'error': 'Camera not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
    
def video_player(request):
    return render(request, 'video.html')

def live_stream(request):
    return render(request, 'live_stream.html')

def all_cameras_stream(request):
    departement_id = request.GET.get('departement_id')
    departements = Lieu.objects.all()  # Tous les départements (Lieu)

    if departement_id:
        cameras = Camera.objects.filter(department_id=departement_id)
    else:
        cameras = Camera.objects.all()

    # Démarrer les threads pour les caméras qui n'ont pas encore de thread actif
    for camera in cameras:
        if camera.id not in running_threads:
            start_camera_thread(camera.id, camera.rtsp_url)

    context = {
        'cameras': cameras,
        'departements': departements,
        'selected_departement_id': departement_id,
    }
    return render(request, 'all_cameras.html', context)