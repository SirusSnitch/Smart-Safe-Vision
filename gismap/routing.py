from django.urls import path
from .consumers import NotificationConsumer, CameraStreamConsumer

websocket_urlpatterns = [
    # Notifications
    path("ws/notifications/", NotificationConsumer.as_asgi()),

    # Camera streaming (dynamic camera_id)
    path("ws/stream/<int:camera_id>/", CameraStreamConsumer.as_asgi()),
]
