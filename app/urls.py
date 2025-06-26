from django.urls import path
from .views import index, save_polygon, get_polygons

urlpatterns = [
    path('', index, name='index'),
    path('save-polygon/', save_polygon, name='save_polygon'),
    path('get-polygons/', get_polygons, name='get_polygons'),
]
