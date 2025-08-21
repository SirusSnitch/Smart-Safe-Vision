import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from channels.middleware import BaseMiddleware
import gismap.routing  # your websocket routes

# Set Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smartVision.settings')

# HTTP app (Django)
django_asgi_app = get_asgi_application()

# --- HTTP Logging Middleware (Django style, better in settings.py normally) ---
class HttpLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        print(f"[HTTP] {request.method} {request.path}")
        response = self.get_response(request)
        print(f"[HTTP] Response {response.status_code}")
        return response

# --- WebSocket Logging Middleware ---
class WebSocketLoggingMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        print(f"[WebSocket] New connection at {scope['path']}")
        try:
            return await super().__call__(scope, receive, send)
        finally:
            print(f"[WebSocket] Connection closed at {scope['path']}")

# --- Main ASGI application ---
application = ProtocolTypeRouter({
    "http": django_asgi_app,  # Handles normal HTTP requests
    "websocket": AuthMiddlewareStack(
        WebSocketLoggingMiddleware(  # Log WebSocket connections
            URLRouter(
                gismap.routing.websocket_urlpatterns
            )
        )
    ),
})
