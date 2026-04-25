"""Tests for ``apps.realtime.tasks.fetch_iett_positions``.

Celery is not started — the task is called as a plain function. Redis
is faked via ``fakeredis`` (shared client so pub/sub state is visible
to the test subscriber). The IETT adapter is replaced wholesale via
``_make_adapter`` monkey-patch — no network, no rate-limiter wiring.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from types import SimpleNamespace

import fakeredis
import pytest
import requests

from apps.realtime import tasks as tasks_module
from apps.realtime.adapters.iett_soap import IettRateLimitViolation
from apps.realtime.schemas import VehiclePosition
from apps.realtime.tasks import (
    MAPPING_CACHE_KEY,
    UNMAPPED_COUNT_KEY,
    VEHICLES_CACHE_KEY_PREFIX,
    VEHICLES_CACHE_TTL_SECONDS,
    fetch_iett_positions,
)

LOGGER_NAME = "apps.realtime.tasks"


# --- fixtures --------------------------------------------------------------


@pytest.fixture
def fake_redis(monkeypatch):
    """Shared FakeStrictRedis: same instance for the task client and the
    test's pub/sub subscriber, so PUBLISH inside the task delivers."""
    client = fakeredis.FakeStrictRedis()
    monkeypatch.setattr(
        tasks_module.redis, "from_url",
        lambda *a, **kw: client,
    )
    return client


@pytest.fixture
def patch_adapter(monkeypatch):
    """Return a setter that swaps ``_make_adapter`` for a stub returning
    a SimpleNamespace whose ``fetch`` returns / raises whatever the test
    needs. Avoids wiring real limiters."""
    def _set(fetch_return=None, fetch_raises=None):
        def _fetch():
            if fetch_raises is not None:
                raise fetch_raises
            return fetch_return or []
        adapter = SimpleNamespace(fetch=_fetch)
        monkeypatch.setattr(
            tasks_module, "_make_adapter", lambda redis_client: adapter,
        )
        return adapter
    return _set


# --- helpers ---------------------------------------------------------------


def _ts_from_ms(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def _make_vehicle(
    vehicle_id: str,
    ts_ms: int = 5000,
    *,
    latitude: float = 41.0,
    longitude: float = 29.0,
    speed: float | None = None,
    bearing: float | None = None,
) -> VehiclePosition:
    return VehiclePosition(
        vehicle_id=vehicle_id,
        latitude=latitude,
        longitude=longitude,
        bearing=bearing,
        speed=speed,
        timestamp=_ts_from_ms(ts_ms),
        source="iett-soap",
        mode="bus",
    )


def _interval(start_ms: int, end_ms: int, hat: str, guzergah: str | None = None) -> dict:
    return {
        "start_ms": start_ms,
        "end_ms": end_ms,
        "hat": hat,
        "guzergah": guzergah or f"{hat}_G_D0",
    }


def _seed_mapping(client, by_kapi: dict) -> None:
    """Write a valid mapping payload to ``iett:mapping:current``."""
    active = sorted({iv["hat"] for ivs in by_kapi.values() for iv in ivs})
    payload = {
        "date": "2026-04-22",
        "by_kapi": by_kapi,
        "active_routes": active,
        "routes_by_mode": {"metrobus": [], "bus": active},
    }
    client.set(MAPPING_CACHE_KEY, json.dumps(payload).encode("utf-8"))


def _subscribe(client, *channels) -> object:
    """Subscribe to channels and drain the subscribe-ack messages."""
    pubsub = client.pubsub()
    pubsub.subscribe(*channels)
    for _ in channels:
        ack = pubsub.get_message(timeout=1.0)
        assert ack is not None and ack["type"] == "subscribe"
    return pubsub


def _drain_messages(pubsub, expected_count: int, timeout: float = 1.0) -> list[dict]:
    """Pull up to ``expected_count`` ``message``-type frames from pubsub."""
    out: list[dict] = []
    while len(out) < expected_count:
        msg = pubsub.get_message(timeout=timeout)
        if msg is None:
            break
        if msg.get("type") == "message":
            out.append(msg)
    return out


# --- 1. happy path --------------------------------------------------------


def test_happy_path_single_route_single_vehicle(fake_redis, patch_adapter):
    _seed_mapping(fake_redis, {"A-231": [_interval(1000, 99999, "29B")]})
    patch_adapter(fetch_return=[_make_vehicle("A-231", ts_ms=5000, speed=24.0)])

    pubsub = _subscribe(fake_redis, "vehicles:route:29B")
    result = fetch_iett_positions()
    msgs = _drain_messages(pubsub, expected_count=1)

    assert len(msgs) == 1
    payload = json.loads(msgs[0]["data"])
    assert payload["type"] == "route_vehicles_update"
    assert payload["route_id"] == "29B"
    assert len(payload["vehicles"]) == 1
    assert payload["vehicles"][0]["id"] == "A-231"

    cached = fake_redis.get("vehicles:route:29B")
    assert cached is not None
    assert json.loads(cached) == payload

    assert int(fake_redis.get(UNMAPPED_COUNT_KEY)) == 0
    assert result["status"] == "ok"
    assert result["fetched"] == 1
    assert result["unmapped"] == 0
    assert result["routes"] == 1


# --- 2. multi-route grouping ----------------------------------------------


def test_multiple_routes_grouped_correctly(fake_redis, patch_adapter):
    _seed_mapping(fake_redis, {
        "A-231": [_interval(1000, 99999, "29B")],
        "B-100": [_interval(1000, 99999, "34BZ")],
        "C-50":  [_interval(1000, 99999, "29B")],
    })
    patch_adapter(fetch_return=[
        _make_vehicle("A-231"),
        _make_vehicle("B-100"),
        _make_vehicle("C-50"),
    ])

    pubsub = _subscribe(
        fake_redis, "vehicles:route:29B", "vehicles:route:34BZ",
    )
    result = fetch_iett_positions()
    msgs = _drain_messages(pubsub, expected_count=2)

    assert len(msgs) == 2
    by_route: dict[str, list] = {}
    for msg in msgs:
        payload = json.loads(msg["data"])
        by_route[payload["route_id"]] = payload["vehicles"]

    assert {v["id"] for v in by_route["29B"]} == {"A-231", "C-50"}
    assert {v["id"] for v in by_route["34BZ"]} == {"B-100"}
    assert result["routes"] == 2


# --- 3. unmapped vehicle skipped from pub ---------------------------------


def test_unmapped_vehicle_skipped_from_pub(fake_redis, patch_adapter):
    _seed_mapping(fake_redis, {"A-231": [_interval(1000, 9999, "29B")]})
    patch_adapter(fetch_return=[
        _make_vehicle("A-231", ts_ms=5000),
        _make_vehicle("X-999", ts_ms=5000),  # not in mapping
    ])

    pubsub = _subscribe(fake_redis, "vehicles:route:29B")
    result = fetch_iett_positions()
    msgs = _drain_messages(pubsub, expected_count=1)

    assert len(msgs) == 1
    payload = json.loads(msgs[0]["data"])
    assert {v["id"] for v in payload["vehicles"]} == {"A-231"}

    assert int(fake_redis.get(UNMAPPED_COUNT_KEY)) == 1
    assert fake_redis.exists("vehicles:route:None") == 0
    assert result["unmapped"] == 1
    assert result["routes"] == 1


# --- 4. cache miss → all unmapped, no pub ---------------------------------


def test_mapping_cache_miss_all_unmapped_no_pub(fake_redis, patch_adapter, caplog):
    # Note: we deliberately do NOT seed the mapping key.
    patch_adapter(fetch_return=[
        _make_vehicle("A-231"),
        _make_vehicle("B-100"),
        _make_vehicle("C-50"),
    ])

    pubsub = _subscribe(fake_redis, "vehicles:route:29B")

    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        result = fetch_iett_positions()

    msgs = _drain_messages(pubsub, expected_count=1, timeout=0.2)
    assert msgs == []
    assert fake_redis.keys("vehicles:route:*") == []

    assert int(fake_redis.get(UNMAPPED_COUNT_KEY)) == 3
    assert result["unmapped"] == 3
    assert result["routes"] == 0

    miss_warnings = [
        r.getMessage() for r in caplog.records
        if r.levelno == logging.WARNING and "mapping cache miss" in r.getMessage()
    ]
    assert len(miss_warnings) == 1


# --- 5. adapter failure branches → graceful return ------------------------


def test_adapter_generic_exception_returns_error(fake_redis, patch_adapter, caplog):
    _seed_mapping(fake_redis, {"A-231": [_interval(1000, 99999, "29B")]})
    patch_adapter(fetch_raises=RuntimeError("upstream exploded"))

    with caplog.at_level(logging.ERROR, logger=LOGGER_NAME):
        result = fetch_iett_positions()

    assert result["status"] == "error"
    assert result["error_type"] == "RuntimeError"
    assert "upstream exploded" in result["error"]

    assert fake_redis.keys("vehicles:route:*") == []
    assert fake_redis.get(UNMAPPED_COUNT_KEY) is None

    # Generic branch uses logger.exception → exc_info attached.
    exc_records = [r for r in caplog.records if r.exc_info is not None]
    assert len(exc_records) >= 1


def test_adapter_rate_limit_violation_returns_error(fake_redis, patch_adapter, caplog):
    _seed_mapping(fake_redis, {"A-231": [_interval(1000, 99999, "29B")]})
    patch_adapter(fetch_raises=IettRateLimitViolation("budget exhausted"))

    with caplog.at_level(logging.ERROR, logger=LOGGER_NAME):
        result = fetch_iett_positions()

    assert result["status"] == "error"
    assert result["error_type"] == "rate_limit_violation"
    assert "budget exhausted" in result["error"]

    assert fake_redis.keys("vehicles:route:*") == []
    assert fake_redis.get(UNMAPPED_COUNT_KEY) is None

    # Rate-limit branch uses logger.error (no exc_info).
    err_records = [
        r for r in caplog.records
        if r.levelno == logging.ERROR and "rate-limit violation" in r.getMessage()
    ]
    assert len(err_records) == 1


def test_adapter_http_error_returns_error(fake_redis, patch_adapter, caplog):
    _seed_mapping(fake_redis, {"A-231": [_interval(1000, 99999, "29B")]})
    patch_adapter(fetch_raises=requests.HTTPError("502 Bad Gateway"))

    with caplog.at_level(logging.ERROR, logger=LOGGER_NAME):
        result = fetch_iett_positions()

    assert result["status"] == "error"
    assert result["error_type"] == "http_error"
    assert "502" in result["error"]

    assert fake_redis.keys("vehicles:route:*") == []
    assert fake_redis.get(UNMAPPED_COUNT_KEY) is None

    err_records = [
        r for r in caplog.records
        if r.levelno == logging.ERROR and "upstream HTTP error" in r.getMessage()
    ]
    assert len(err_records) == 1


# --- 6. empty fleet → no pub ---------------------------------------------


def test_empty_vehicle_list_no_pub(fake_redis, patch_adapter):
    _seed_mapping(fake_redis, {"A-231": [_interval(1000, 99999, "29B")]})
    patch_adapter(fetch_return=[])

    pubsub = _subscribe(fake_redis, "vehicles:route:29B")
    result = fetch_iett_positions()
    msgs = _drain_messages(pubsub, expected_count=1, timeout=0.2)

    assert msgs == []
    assert fake_redis.keys("vehicles:route:*") == []
    assert int(fake_redis.get(UNMAPPED_COUNT_KEY)) == 0

    assert result["fetched"] == 0
    assert result["unmapped"] == 0
    assert result["routes"] == 0


# --- 7. payload format matches spec §5.3 ----------------------------------


def test_payload_format_matches_spec(fake_redis, patch_adapter):
    _seed_mapping(fake_redis, {"A-231": [_interval(1000, 99999, "29B")]})
    patch_adapter(fetch_return=[
        _make_vehicle("A-231", ts_ms=5000, speed=24.0, bearing=None,
                      latitude=41.04885, longitude=29.10322),
    ])

    pubsub = _subscribe(fake_redis, "vehicles:route:29B")
    fetch_iett_positions()
    msgs = _drain_messages(pubsub, expected_count=1)

    raw = msgs[0]["data"]
    assert b'"bearing":null' in raw  # JSON null literal, not "None"

    payload = json.loads(raw)
    assert set(payload) == {"type", "route_id", "timestamp", "vehicles"}
    assert payload["timestamp"].endswith("Z")
    # Sanity: parses back as ISO 8601 once we restore the +00:00 form.
    datetime.fromisoformat(payload["timestamp"].replace("Z", "+00:00"))

    veh = payload["vehicles"][0]
    assert set(veh) == {"id", "lat", "lon", "bearing", "speed"}
    assert veh["bearing"] is None
    assert veh["speed"] == 24.0
    assert veh["lat"] == 41.04885
    assert veh["lon"] == 29.10322


# --- 8. SET + PUBLISH both happen, TTL ~120s ------------------------------


def test_set_and_publish_both_called(fake_redis, patch_adapter):
    _seed_mapping(fake_redis, {"A-231": [_interval(1000, 99999, "29B")]})
    patch_adapter(fetch_return=[_make_vehicle("A-231")])

    pubsub = _subscribe(fake_redis, "vehicles:route:29B")
    fetch_iett_positions()
    msgs = _drain_messages(pubsub, expected_count=1)
    assert len(msgs) == 1  # PUBLISH happened

    cached = fake_redis.get("vehicles:route:29B")
    assert cached is not None  # SET happened

    ttl = fake_redis.ttl("vehicles:route:29B")
    assert VEHICLES_CACHE_TTL_SECONDS - 5 <= ttl <= VEHICLES_CACHE_TTL_SECONDS


# --- 9. multi-route pipeline smoke (no cross-contamination) --------------


def test_multi_route_pipeline_smoke(fake_redis, patch_adapter):
    routes = ["29B", "34BZ", "15SK", "500T", "M2"]
    by_kapi = {}
    vehicles = []
    for i, hat in enumerate(routes):
        for j in range(2):
            kapi = f"{hat}-{j}"
            by_kapi[kapi] = [_interval(1000, 99999, hat)]
            vehicles.append(_make_vehicle(kapi))

    _seed_mapping(fake_redis, by_kapi)
    patch_adapter(fetch_return=vehicles)

    channels = [f"vehicles:route:{r}" for r in routes]
    pubsub = _subscribe(fake_redis, *channels)

    result = fetch_iett_positions()
    msgs = _drain_messages(pubsub, expected_count=5)

    assert len(msgs) == 5
    seen: dict[str, set[str]] = {}
    for msg in msgs:
        payload = json.loads(msg["data"])
        seen[payload["route_id"]] = {v["id"] for v in payload["vehicles"]}

    assert set(seen) == set(routes)
    for hat, ids in seen.items():
        assert ids == {f"{hat}-0", f"{hat}-1"}, (
            f"route {hat} got {ids}, expected exactly its own two vehicles"
        )

    assert result["routes"] == 5
    assert result["fetched"] == 10


# --- 10. unmapped count overwrites previous tick --------------------------


def test_unmapped_count_overwrites_previous_tick(fake_redis, patch_adapter):
    fake_redis.set(UNMAPPED_COUNT_KEY, 999)

    _seed_mapping(fake_redis, {"A-231": [_interval(1000, 99999, "29B")]})
    patch_adapter(fetch_return=[_make_vehicle("A-231")])

    fetch_iett_positions()

    assert int(fake_redis.get(UNMAPPED_COUNT_KEY)) == 0
