from django.urls import path
from .views import index, save_polygon, get_polygons, save_camera, get_cameras, delete_camera


urlpatterns = [
    path('', index, name='index'),
    path('save-polygon/', save_polygon, name='save_polygon'),
    path('get-polygons/', get_polygons, name='get_polygons'),
    path('save-camera/', save_camera, name='save_camera'),
    path('get-cameras/', get_cameras, name='get_cameras'),
    path('delete-camera/<int:camera_id>/', delete_camera, name='delete_camera'),
]
