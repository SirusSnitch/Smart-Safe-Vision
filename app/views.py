from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
import json
from django.contrib.gis.geos import GEOSGeometry
from .models import Lieu, Camera
from django.core.exceptions import ObjectDoesNotExist

def index(request):
    return render(request, 'index.html')

@csrf_exempt
def save_polygon(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        name = data.get('name')
        geojson = data.get('polygon')

        if not name or not geojson:
            return JsonResponse({'error': 'Invalid data'}, status=400)

        try:
            geom = GEOSGeometry(json.dumps(geojson))
            lieu = Lieu(name=name, polygon=geom)
            lieu.save()
            return JsonResponse({'message': 'Polygon saved!'})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({'error': 'Method not allowed'}, status=405)

def get_polygons(request):
    if request.method == 'GET':
        lieux = Lieu.objects.all()
        features = []
        for lieu in lieux:
            features.append({
                "type": "Feature",
                "geometry": json.loads(lieu.polygon.geojson),
                "properties": {"name": lieu.name}
            })
        return JsonResponse({"type": "FeatureCollection", "features": features})
    return JsonResponse({'error': 'Method not allowed'}, status=405)


@csrf_exempt
def save_camera(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            cam_id = data.get('id')  # if updating
            name = data['name']
            url = data['url']
            coords = data['location']  # [lng, lat]

            point = GEOSGeometry(f'POINT({coords[0]} {coords[1]})')

            if cam_id:
                # update existing
                camera = Camera.objects.get(id=cam_id)
                camera.name = name
                camera.url = url
                camera.location = point
            else:
                # create new
                camera = Camera(name=name, url=url, location=point)
            camera.save()

            return JsonResponse({'success': True, 'id': camera.id})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Method not allowed'}, status=405)


def get_cameras(request):
    if request.method == 'GET':
        features = []
        for cam in Camera.objects.all():
            features.append({
                "type": "Feature",
                "geometry": json.loads(cam.location.geojson),
                "properties": {
                    "id": cam.id,
                    "name": cam.name,
                    "url": cam.url
                }
            })
        return JsonResponse({"type": "FeatureCollection", "features": features})
    return JsonResponse({'error': 'Method not allowed'}, status=405)


@csrf_exempt
def delete_camera(request, camera_id):
    if request.method == 'DELETE':
        try:
            camera = Camera.objects.get(id=camera_id)
            camera.delete()
            return JsonResponse({'success': True})
        except ObjectDoesNotExist:
            return JsonResponse({'error': 'Camera not found'}, status=404)
    return JsonResponse({'error': 'Method not allowed'}, status=405)


def map_view(request):
    return render(request, 'map.html')

