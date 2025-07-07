# waitingproj/asgi.py
import os
from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

# Set the DJANGO_SETTINGS_MODULE environment variable
# This tells Django where to find your project's settings.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'waitingproj.settings')

# Get the Django ASGI application (handles HTTP requests)
# This call initializes Django's settings and app registry.
django_asgi_app = get_asgi_application()

# Import your app's routing AFTER Django's ASGI application is initialized.
import waitingroom.routing

application = ProtocolTypeRouter({
    "http": django_asgi_app, # HTTP requests handled by Django's ASGI app
    "websocket": AuthMiddlewareStack( # WebSocket requests handled by Channels
        URLRouter(
            waitingroom.routing.websocket_urlpatterns # Your app's WebSocket URL patterns
        )
    ),
})
