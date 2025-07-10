import os

# 1. Définit d'abord DJANGO_SETTINGS_MODULE
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smartVision.settings')

# 2. Puis importe Django
from django.core.asgi import get_asgi_application
from django.conf import settings

print("STATICFILES_DIRS[0] =", settings.STATICFILES_DIRS[0])
print("Type of STATICFILES_DIRS[0] =", type(settings.STATICFILES_DIRS[0]))

django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

import gismap.routing

from starlette.middleware.base import BaseHTTPMiddleware

class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        print(f"Request URL: {request.url}")
        response = await call_next(request)
        print(f"Response status: {response.status_code}")
        return response

# Configuration simplifiée - laissons Django gérer les fichiers statiques
application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter(
            gismap.routing.websocket_urlpatterns
        )
    ),
})

# Ajoute le middleware de logging autour de application
application = LoggingMiddleware(application)