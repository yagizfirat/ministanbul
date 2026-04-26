"""HTTP views for realtime app. WebSocket consumer'ları routing.py'de."""
from django.shortcuts import render


def ws_smoke(request):
    """Faz 3 Adım 6b-iv — WebSocket echo connectivity test sayfası."""
    return render(request, "realtime_ws_smoke.html")
