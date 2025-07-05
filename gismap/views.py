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
            url = data.get('url')
            coordinates = data.get('coordinates')  # [lng, lat]

            if not name or not url or not coordinates:
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
                url=url,
                location=point,
                department=department
            )

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
                        "url": cam.url,
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