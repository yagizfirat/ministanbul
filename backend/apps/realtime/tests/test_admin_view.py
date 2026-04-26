"""Tests for the Live Vehicles admin dashboard (Phase 2 Step 5f).

The view itself is read-only over Redis and the adapter's ``health()``
snapshot. We use ``fakeredis`` for state and a ``SimpleNamespace`` stub
for the adapter so no live HTTP / no rate-limiter wiring leaks in.

Auth is exercised by the ``Client`` fixture: anonymous → redirect,
``force_login`` with ``is_staff=True`` → 200.
"""
from __future__ import annotations

import json

import fakeredis
import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from apps.realtime import admin_views
from apps.realtime.tasks import (
    LAST_FETCH_TS_KEY,
    MAPPING_CACHE_KEY,
    UNMAPPED_COUNT_KEY,
)

LIVE_URL = "/admin/live-vehicles/"


# --- fixtures --------------------------------------------------------------


@pytest.fixture
def staff_user(db):
    User = get_user_model()
    return User.objects.create_user(
        username="admin", password="x", is_staff=True, is_superuser=True,
    )


@pytest.fixture
def client_logged_in(staff_user):
    c = Client()
    c.force_login(staff_user)
    return c


@pytest.fixture
def fake_redis(monkeypatch):
    fake = fakeredis.FakeStrictRedis()
    monkeypatch.setattr(admin_views.redis, "from_url", lambda *a, **kw: fake)
    return fake


@pytest.fixture
def patch_adapter(monkeypatch):
    """Replace ``_make_adapter`` with a stub returning a fixed health dict."""
    def _setter(health_payload=None):
        payload = health_payload if health_payload is not None else _make_health()

        class StubAdapter:
            def health(self):
                return payload

        monkeypatch.setattr(
            admin_views, "_make_adapter", lambda r: StubAdapter(),
        )
    return _setter


# --- helpers ---------------------------------------------------------------


def _make_health(fleet_count: int = 10, fleet_status: str = "OK") -> dict:
    return {
        "adapter": "iett-soap",
        "fleet_limiter": {
            "status": fleet_status,
            "count": fleet_count,
            "soft": 60,
            "hard": 72,
            "remaining": 72 - fleet_count,
            "window_seconds": 2400,
            "cooldown_active": False,
            "cooldown_expires_at": None,
        },
        "arsiv_limiter": {
            "status": "OK",
            "count": 1,
            "soft": 60,
            "hard": 72,
            "remaining": 71,
            "window_seconds": 2400,
            "cooldown_active": False,
            "cooldown_expires_at": None,
        },
    }


def _seed_vehicles_all(redis_client, route_counts: dict) -> None:
    """Seed vehicles:all with a synthetic snapshot (Faz 3 6c+ format).

    ``route_counts`` maps route_id (str or None) → vehicle count.
    None key produces unmapped vehicles (route_id null in payload) so
    tests can exercise the "(unmapped)" bucket invariant directly.
    """
    vehicles: list[dict] = []
    seq = 0
    for route_id, count in route_counts.items():
        for _ in range(count):
            vehicles.append({
                "id": f"K-{seq}",
                "lat": 41.0,
                "lon": 29.0,
                "bearing": None,
                "speed": None,
                "route_id": route_id,
            })
            seq += 1
    mapped = sum(c for r, c in route_counts.items() if r is not None)
    payload = json.dumps({
        "type": "vehicles_all_update",
        "timestamp": "2026-04-25T12:00:00Z",
        "vehicle_count": len(vehicles),
        "mapped_count": mapped,
        "vehicles": vehicles,
    })
    redis_client.set("vehicles:all", payload)


def _seed_mapping(
    redis_client,
    *,
    ttl_seconds: int = 100000,
    snapshot_date: str = "2026-04-25",
    snapshot_day_type: str = "saturday",
) -> None:
    """Seed iett:mapping:current with a 5i-i+ format payload.

    snapshot_date defaults to a Saturday (2026-04-25) so the default
    snapshot_day_type='saturday' is consistent. Override either when a
    test needs to exercise the 5i-iv snapshot-metadata display branch."""
    payload = json.dumps({
        "snapshot_date": snapshot_date,
        "snapshot_day_type": snapshot_day_type,
        "by_kapi": {},
        "active_routes": [],
        "routes_by_mode": {"metrobus": [], "bus": []},
    }).encode("utf-8")
    redis_client.set(MAPPING_CACHE_KEY, payload, ex=ttl_seconds)


# --- 1. unauthenticated → redirect ----------------------------------------


def test_unauthenticated_redirects(db, fake_redis, patch_adapter):
    patch_adapter()
    c = Client()
    response = c.get(LIVE_URL)
    assert response.status_code == 302
    assert "/admin/login/" in response.url


# --- 2. authenticated render ---------------------------------------------


def test_authenticated_renders_200(client_logged_in, fake_redis, patch_adapter):
    _seed_mapping(fake_redis)
    _seed_vehicles_all(fake_redis, {"29B": 1})
    patch_adapter()

    response = client_logged_in.get(LIVE_URL)
    assert response.status_code == 200

    body = response.content.decode("utf-8")
    assert "Live Vehicles" in body
    assert "Total active vehicles" in body
    assert "29B" in body


# --- 3. total vehicle aggregation + ranking -------------------------------


def test_total_vehicle_count_aggregates(
    client_logged_in, fake_redis, patch_adapter,
):
    _seed_vehicles_all(fake_redis, {"29B": 5, "34BZ": 3, "M2": 2})
    patch_adapter()

    response = client_logged_in.get(LIVE_URL)
    body = response.content.decode("utf-8")

    assert "Total active vehicles" in body
    assert ">10<" in body  # rendered cell shows 10 (5+3+2)

    # 29B (5 vehicles) ranks above 34BZ (3) and M2 (2).
    pos_29b = body.find(">29B<")
    pos_34bz = body.find(">34BZ<")
    pos_m2 = body.find(">M2<")
    assert 0 < pos_29b < pos_34bz < pos_m2


# --- 3b. UX pivot invariant: unmapped vehicles visible in top_routes ------


def test_top_routes_includes_unmapped_bucket(
    client_logged_in, fake_redis, patch_adapter,
):
    """UX pivot invariant: unmapped vehicles MUST appear in top_routes
    as a distinct '(unmapped)' bucket — operators see mapping issues
    instead of silent missing vehicles. Pre-pivot the per-route fanout
    dropped them from per-route keys; vehicles:all + Counter exposes
    them as a None bucket rendered '(unmapped)' in the template."""
    _seed_vehicles_all(fake_redis, {"29B": 5, None: 3})
    patch_adapter()

    response = client_logged_in.get(LIVE_URL)
    body = response.content.decode("utf-8")

    assert ">29B<" in body
    assert "(unmapped)" in body
    # 29B (5) ranks above unmapped (3); ordering preserved by Counter
    # most_common semantics in admin_views.
    pos_29b = body.find(">29B<")
    pos_unmapped = body.find("(unmapped)")
    assert 0 < pos_29b < pos_unmapped


# --- 4. unmapped count + percent ------------------------------------------


def test_unmapped_count_and_percent(
    client_logged_in, fake_redis, patch_adapter,
):
    _seed_vehicles_all(fake_redis, {"29B": 10})
    fake_redis.set(UNMAPPED_COUNT_KEY, 5)
    patch_adapter()

    response = client_logged_in.get(LIVE_URL)
    body = response.content.decode("utf-8")

    # 5 unmapped / (10 mapped + 5 unmapped) = 33.3%
    assert "5 (33.3%)" in body


# --- 5. mapping cache present + TTL display --------------------------------


def test_mapping_cache_present(client_logged_in, fake_redis, patch_adapter):
    _seed_mapping(fake_redis, ttl_seconds=100000)  # 100000/3600 = 27.78 → "27.8"
    patch_adapter()

    response = client_logged_in.get(LIVE_URL)
    body = response.content.decode("utf-8")

    assert "present" in body
    assert "27.8 h remaining" in body
    assert "MISSING" not in body


# --- 6. mapping cache missing → red MISSING ------------------------------


def test_mapping_cache_missing(client_logged_in, fake_redis, patch_adapter):
    # Note: no _seed_mapping — key absent.
    patch_adapter()

    response = client_logged_in.get(LIVE_URL)
    body = response.content.decode("utf-8")

    assert "MISSING" in body
    assert 'color: red' in body


# --- 7. rate limit numbers rendered --------------------------------------


def test_rate_limit_status_displayed(
    client_logged_in, fake_redis, patch_adapter,
):
    patch_adapter(_make_health(fleet_count=44, fleet_status="OK"))

    response = client_logged_in.get(LIVE_URL)
    body = response.content.decode("utf-8")

    assert "44 / 72" in body
    assert "28 remaining" in body
    # Status cell: a row whose value is exactly "OK".
    assert ">OK<" in body


# --- 8. empty state messages ---------------------------------------------


def test_no_active_routes_message(
    client_logged_in, fake_redis, patch_adapter,
):
    # No vehicles, no mapping seeded.
    patch_adapter()

    response = client_logged_in.get(LIVE_URL)
    body = response.content.decode("utf-8")

    assert "No active routes" in body
    assert "MISSING" in body


# --- 9. Mapping snapshot metadata + mismatch counter (5i-iv) ------------


def test_mapping_snapshot_metadata_displayed(
    client_logged_in, fake_redis, patch_adapter,
):
    """5i-iv: admin shows mapping kaynağı (snapshot day_type + date)."""
    _seed_mapping(
        fake_redis,
        snapshot_date="2026-04-22",
        snapshot_day_type="weekday",
    )
    patch_adapter()

    response = client_logged_in.get(LIVE_URL)
    body = response.content.decode("utf-8")

    assert "Mapping kaynağı" in body
    assert "weekday" in body
    assert "2026-04-22" in body
    # mapping_age_days >= 0 — exact day delta depends on real today, so
    # just check the "X gün eski" suffix appears once age has been computed.
    assert "gün eski" in body


def test_mismatch_counter_displayed_with_orange_alert(
    client_logged_in, fake_redis, patch_adapter,
):
    """5i-iv: counter > 0 renders orange-bold; counter == 0 plain."""
    fake_redis.set("stats:day_type_mismatch_count", 7)
    _seed_mapping(fake_redis)
    patch_adapter()

    response = client_logged_in.get(LIVE_URL)
    body = response.content.decode("utf-8")

    assert "Day-type mismatch count" in body
    # Orange-bold form: <strong style="color: orange;">7</strong>
    assert 'color: orange' in body
    assert ">7</strong>" in body
