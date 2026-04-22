"""ASGI entry point — used by Daphne/Uvicorn. WebSocket routing added in Faz 3."""
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

application = get_asgi_application()
