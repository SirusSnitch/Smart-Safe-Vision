from django.urls import path

from .views import index, save_polygon, get_polygons, delete_polygon,get_isgb_polygon, get_cameras, delete_camera,save_camera,video_player,live_stream,all_cameras_stream, sign_in
from .streaming_views import all_cameras_stream,stream_camera_view

from .views import test_notification_view
from . import views
from .views import notification_dashboard



urlpatterns = [
    path('', sign_in, name='sign_in'),  # Login page par défaut
    path('dashboard/', index, name='index'),  # Page carte protégée
    path('get-isgb-polygon/', get_isgb_polygon, name='get_isgb_polygon'),
    path('save-polygon/', save_polygon, name='save_polygon'),
    path('get-polygons/', get_polygons, name='get_polygons'),
    path('delete-polygon/<int:polygon_id>/', delete_polygon, name='delete_polygon'),
    path('get_cameras/', get_cameras, name='get_cameras'),
    path('delete_camera/<int:camera_id>/', delete_camera, name='delete_camera'),
    path('save_camera/', save_camera, name='save_camera'),
    path('video/', video_player, name='video_player'),
    path('live/', live_stream, name='live_stream'),
    path('all-cameras/', all_cameras_stream, name='all_cameras_stream'),
    path('stream/<int:camera_id>/', stream_camera_view, name='stream_camera_view'),

    path("test-notif/", test_notification_view, name="test_notification"),
# Nouvelles URLs pour les notifications
    #path('notifications/', views.notification_dashboard, name='notifications'),
   # path('api/detections/', views.get_recent_detections, name='recent_detections'),
   # path('api/stats/', views.get_dashboard_stats, name='dashboard_stats'),

path('alertes/', notification_dashboard, name='notification_dashboard'),

]



