import threading

from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.contrib.auth import authenticate, login
from django.contrib import messages
import json
from django.contrib.gis.geos import GEOSGeometry, Point
from .models import Lieu, Camera
import os
from django.conf import settings
import traceback
from django.views.decorators.http import require_http_methods
from django.core.serializers import serialize
from django.contrib.gis.serializers import geojson
import cv2
import time

# global dict to track running threads
running_threads = {}


def process_camera_stream(camera_id, camera_url):
    print(f"[{camera_id}] Started processing thread for {camera_url}")
    cap = cv2.VideoCapture(camera_url)
    while True:
        ret, frame = cap.read()
        if not ret:
            print(f"[{camera_id}] Failed to get frame")
            time.sleep(1)
            continue

        print(f"[{camera_id}] Frame reçu")

        time.sleep(0.03)  # simulate 30 fps

def start_camera_thread(camera_id, url):
    if camera_id not in running_threads:
        t = threading.Thread(target=process_camera_stream, args=(camera_id, url), daemon=True)
        t.start()
        running_threads[camera_id] = t


# ✅ Vue de connexion (sign in)
def sign_in(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('index')  # redirection vers la carte
        else:
            messages.error(request, "Email ou mot de passe incorrect.")

    return render(request, 'admin/signin.html')


def index(request):
    return render(request, 'map/index.html')


@csrf_exempt
@require_http_methods(["POST"])
def save_polygon(request):
    try:
        data = json.loads(request.body)
        polygon_id = data.get('id')
        name = data.get('name')
        geometry = data.get('geometry')
        area = data.get('area', 0)

        if not name or not geometry:
            return JsonResponse({'error': 'Name and geometry are required'}, status=400)

        geom = GEOSGeometry(json.dumps(geometry))
        if not geom.valid:
            return JsonResponse({'error': 'Invalid geometry'}, status=400)

        if polygon_id:
            lieu = Lieu.objects.get(pk=polygon_id)
            lieu.name = name
            lieu.polygon = geom
            lieu.area = float(area)
            lieu.save()
            message = 'Polygon updated successfully'
        else:
            lieu = Lieu(name=name, polygon=geom, area=float(area))
            lieu.save()
            message = 'Polygon saved successfully'

        return JsonResponse({'status': 'success', 'message': message, 'id': lieu.id})

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
@require_http_methods(["POST"])
def save_camera(request):
    try:
        data = json.loads(request.body)
        camera_id = data.get('id')
        name = data.get('name')
        url = data.get('url')
        coordinates = data.get('coordinates')

        if not name or not url or not coordinates:
            return JsonResponse({'error': 'Name, URL, and coordinates are required'}, status=400)

        point = Point(coordinates[0], coordinates[1])
        department = None
        for lieu in Lieu.objects.all():
            if lieu.polygon.contains(point):
                department = lieu
                break

        if department is None:
            return JsonResponse({
                'status': 'error',
                'message': "La caméra doit être placée à l'intérieur d'un département existant."
            }, status=400)

        if camera_id:
            camera = Camera.objects.get(pk=camera_id)
            camera.name = name
            camera.url = url
            camera.location = point
            camera.department = department
            camera.save()
            message = 'Camera updated successfully'
            start_camera_thread(camera.id, camera.url)

        else:
            camera = Camera.objects.create(
                name=name,
                url=url,
                location=point,
                department=department
            )
            message = 'Camera saved successfully'

        return JsonResponse({
            'status': 'success',
            'message': message,
            'id': camera.id,
            'department_id': department.id
        })

    except Camera.DoesNotExist:
        return JsonResponse({'error': 'Camera not found'}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e), 'traceback': traceback.format_exc()}, status=500)


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
                        "url": cam.url,
                        "department_id": cam.department.id if cam.department else None,
                        "department_name": cam.department.name if cam.department else None,
                    },
                    "id": cam.id
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
