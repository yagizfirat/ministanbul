"""HTTP + preview routes for the realtime app (ROADMAP 6b-iv onwards).
WebSocket route'ları routing.py'de (Channels). REST endpoints (6e) ve
Leaflet realtime preview (6f) buraya eklenecek."""
from django.urls import path

from . import views

urlpatterns = [
    path("preview/ws-smoke/", views.ws_smoke, name="realtime-ws-smoke"),
    path("api/vehicles/live/", views.vehicles_live, name="vehicles_live"),
]
