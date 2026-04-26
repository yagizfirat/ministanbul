"""HTTP views for realtime app.

ws_smoke: Faz 3 6b-iv WebSocket echo connectivity test page.
vehicles_live: Faz 3 6e REST fallback for /ws/vehicles/ —
WebSocket'a bağlanamayan client'lar için son vehicles:all
snapshot'ını HTTP üstünden sunar.

WebSocket consumer'ları routing.py'de.
"""
from __future__ import annotations

import json
import logging

import redis
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from .tasks import VEHICLES_ALL_KEY

logger = logging.getLogger(__name__)


def ws_smoke(request):
    """Faz 3 Adım 6b-iv — WebSocket echo connectivity test sayfası."""
    return render(request, "realtime_ws_smoke.html")


@require_GET
def vehicles_live(request):
    """GET /api/vehicles/live/ → vehicles:all snapshot.

    503 if snapshot absent (server warming up or pipeline
    stale). Cache-Control max-age=60 (matches fetch task tick).
    """
    client = redis.from_url(settings.REDIS_URL, decode_responses=False)
    raw = client.get(VEHICLES_ALL_KEY)
    if raw is None:
        # M3.A: 503 — retry semantic. Cache-Control no-store
        # ensures clients don't cache the error response.
        response = JsonResponse(
            {"error": "snapshot_not_ready"},
            status=503,
        )
        response["Cache-Control"] = "no-store"
        return response
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("vehicles_live: corrupt vehicles:all key")
        response = JsonResponse(
            {"error": "snapshot_corrupt"},
            status=503,
        )
        response["Cache-Control"] = "no-store"
        return response
    response = JsonResponse(payload)
    response["Cache-Control"] = "max-age=60"
    return response
