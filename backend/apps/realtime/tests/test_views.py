"""Tests for vehicles_live REST fallback (Faz 3 Adım 6e-ii).

test_admin_view.py ile birebir simetrik fixture pattern: sync
fakeredis monkey-patch + Django test Client. Async test gerekmez,
sync view + sync Redis client.
"""
from __future__ import annotations

import json

import fakeredis
import pytest
from django.test import Client
from django.urls import reverse

from apps.realtime import views as views_module


LIVE_URL = reverse("vehicles_live")  # /api/vehicles/live/


@pytest.fixture
def fake_redis(monkeypatch):
    """sync fakeredis instance, views.py'nin redis.from_url'unu
    bağlar. test_admin_view.py'deki pattern'le simetrik."""
    client = fakeredis.FakeStrictRedis()
    monkeypatch.setattr(
        views_module.redis, "from_url",
        lambda *args, **kwargs: client,
    )
    return client


@pytest.fixture
def http_client():
    return Client()


def _seed_vehicles_all(redis_client, payload: dict) -> None:
    redis_client.set("vehicles:all", json.dumps(payload))


# --- 4 test ---

def test_vehicles_live_returns_snapshot_when_present(
    fake_redis, http_client,
):
    payload = {
        "type": "vehicles_all_update",
        "timestamp": "2026-04-26T08:30:00Z",
        "vehicle_count": 2,
        "mapped_count": 1,
        "vehicles": [
            {"id": "K-1", "lat": 41.0, "lon": 29.0, "bearing": None,
             "speed": None, "route_id": "29B"},
            {"id": "K-2", "lat": 41.1, "lon": 29.1, "bearing": None,
             "speed": None, "route_id": None},
        ],
    }
    _seed_vehicles_all(fake_redis, payload)

    response = http_client.get(LIVE_URL)

    assert response.status_code == 200
    assert response.json() == payload
    assert response["Cache-Control"] == "max-age=60"


def test_vehicles_live_returns_503_when_absent(
    fake_redis, http_client,
):
    # No seed
    response = http_client.get(LIVE_URL)

    assert response.status_code == 503
    assert response.json() == {"error": "snapshot_not_ready"}
    assert response["Cache-Control"] == "no-store"


def test_vehicles_live_returns_503_on_corrupt_payload(
    fake_redis, http_client, caplog,
):
    fake_redis.set("vehicles:all", b"{not valid json")

    with caplog.at_level("WARNING"):
        response = http_client.get(LIVE_URL)

    assert response.status_code == 503
    assert response.json() == {"error": "snapshot_corrupt"}
    assert response["Cache-Control"] == "no-store"
    assert any(
        "corrupt vehicles:all" in record.message
        for record in caplog.records
    )


def test_vehicles_live_only_accepts_GET(http_client):
    """require_GET decorator → POST/PUT/DELETE 405 dönmeli."""
    response = http_client.post(LIVE_URL)

    assert response.status_code == 405
