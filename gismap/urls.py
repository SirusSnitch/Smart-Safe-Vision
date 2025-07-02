from django.urls import path
from .views import index, save_polygon, get_polygons, delete_polygon, get_isgb_polygon, get_cameras

urlpatterns = [
    path('', index, name='index'),
    path('get-isgb-polygon/', get_isgb_polygon, name='get_isgb_polygon'),
    path('save-polygon/', save_polygon, name='save_polygon'),
    path('get-polygons/', get_polygons, name='get_polygons'),
    path('delete-polygon/<int:polygon_id>/', delete_polygon, name='delete_polygon'),
    path('get_cameras/', get_cameras, name='get_cameras'),
]
