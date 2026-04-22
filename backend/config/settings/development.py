"""Development-only settings. Loaded when DJANGO_SETTINGS_MODULE=config.settings.development."""
from .base import *  # noqa: F401, F403

DEBUG = True

INTERNAL_IPS = ["127.0.0.1"]

CORS_ALLOW_ALL_ORIGINS = True

# Frontend dev server (Vite) proxies /api to this backend — no extra host needed
# but keep permissive for quick experimentation.
