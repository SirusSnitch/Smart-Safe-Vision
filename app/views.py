from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
import json
from django.contrib.gis.geos import GEOSGeometry
from .models import Lieu

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
