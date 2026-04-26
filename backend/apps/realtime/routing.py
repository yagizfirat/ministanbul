"""WebSocket URL patterns. EchoConsumer is the smoke target (kept after
6d as an isolated connectivity probe); VehicleAllConsumer is the live
vehicles broadcast endpoint (Faz 3 6d)."""
from django.urls import path
from django.urls.resolvers import URLPattern

from .consumers import EchoConsumer, VehicleAllConsumer

websocket_urlpatterns: list[URLPattern] = [
    path("ws/echo/", EchoConsumer.as_asgi()),
    path("ws/vehicles/", VehicleAllConsumer.as_asgi()),
]
