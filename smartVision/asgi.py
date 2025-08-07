import os
from django.core.asgi import get_asgi_application
from django.conf import settings

# Définit la variable d'environnement pour les settings Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smartVision.settings')

# Import de l'application ASGI Django classique (HTTP)
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

import gismap.routing  # adapte selon ton app

from starlette.middleware.base import BaseHTTPMiddleware

class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        print(f"Request URL: {request.url}")
        response = await call_next(request)
        print(f"Response status: {response.status_code}")
        return response

# Compose le routeur ASGI pour HTTP et WebSocket
application = ProtocolTypeRouter({
    "http": django_asgi_app,  # Requête HTTP classique gérée par Django
    "websocket": AuthMiddlewareStack(  # WebSocket avec authentification utilisateur
        URLRouter(
            gismap.routing.websocket_urlpatterns  # URLs WebSocket définies dans gismap/routing.py
        )
    ),
})

# Ajoute le middleware de logging (optionnel)
application = LoggingMiddleware(application)
