"""WebSocket URL patterns. EchoConsumer is the smoke target;
VehicleAllConsumer joins in 6d."""
from django.urls import path
from django.urls.resolvers import URLPattern

from .consumers import EchoConsumer

websocket_urlpatterns: list[URLPattern] = [
    path("ws/echo/", EchoConsumer.as_asgi()),
]
