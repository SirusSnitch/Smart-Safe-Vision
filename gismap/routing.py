# gismap/routing.py
from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/test/$', consumers.TestConsumer.as_asgi()),
    # Ajoutez d'autres routes WebSocket ici si nécessaire
]