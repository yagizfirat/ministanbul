"""Tests for ``apps.realtime.tasks.fetch_iett_positions`` (vehicles:all model).

Faz 3 Adım 6c'de pipeline tek ``vehicles:all`` snapshot + ``group_send``
modeline indirgendi. Per-route fanout gitti — mapping/enrich/mismatch
katmanları aynen, sadece son adım değişti.

Celery is not started; the task is called as a plain function. Redis
is faked via ``fakeredis`` (writes hit the same client the task reads).
The IETT adapter is replaced wholesale via ``_make_adapter``. The
Channels layer is mocked at the module level so ``async_to_sync(
channel_layer.group_send)`` calls land in a Python list, not Memurai.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import fakeredis
import pytest
import requests

from apps.realtime import tasks as tasks_module
from apps.realtime.adapters.iett_soap import IettRateLimitViolation
from apps.realtime.schemas import VehiclePosition
from apps.realtime.tasks import (
    DAY_TYPE_MISMATCH_COUNT_KEY,
    LAST_FETCH_TS_KEY,
    MAPPING_CACHE_KEY,
    UNMAPPED_COUNT_KEY,
    VEHICLES_ALL_GROUP,
    VEHICLES_ALL_KEY,
    VEHICLES_CACHE_TTL_SECONDS,
    fetch_iett_positions,
)

ISTANBUL_TZ = ZoneInfo("Europe/Istanbul")
LOGGER_NAME = "apps.realtime.tasks"


# --- fixtures --------------------------------------------------------------


@pytest.fixture
def fake_redis(monkeypatch):
    """Shared FakeStrictRedis: same instance for the task client and the
    test's reader, so SET inside the task is observable."""
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


@pytest.fixture(autouse=True)
def captured_group_sends(monkeypatch):
    """Capture ``channel_layer.group_send`` calls into a Python list.

    Autouse: every test gets the mock — even the ones that don't read the
    list. Without it the real RedisChannelLayer would try to talk to
    Memurai db=1, leaking pipeline output across tests.
    """
    sent: list[tuple[str, dict]] = []

    async def fake_group_send(group, message):
        sent.append((group, message))

    layer = SimpleNamespace(group_send=fake_group_send)
    monkeypatch.setattr(
        tasks_module, "get_channel_layer", lambda: layer,
    )
    return sent


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


def _interval(start_sec: int, end_sec: int, hat: str, guzergah: str | None = None) -> dict:
    return {
        "start_sec": start_sec,
        "end_sec": end_sec,
        "hat": hat,
        "guzergah": guzergah or f"{hat}_G_D0",
    }


def _seed_mapping(
    client,
    by_kapi: dict,
    *,
    snapshot_date: str = "1970-01-01",
    snapshot_day_type: str = "sunday",
) -> None:
    """See test_fetch_task.py history: snapshot_date 1970-01-01 + day_type
    'sunday' is the default that keeps the 5i-iv mismatch detection silent
    against ``_make_vehicle(ts_ms=...)``-derived timestamps."""
    active = sorted({iv["hat"] for ivs in by_kapi.values() for iv in ivs})
    payload = {
        "snapshot_date": snapshot_date,
        "snapshot_day_type": snapshot_day_type,
        "by_kapi": by_kapi,
        "active_routes": active,
        "routes_by_mode": {"metrobus": [], "bus": active},
    }
    client.set(MAPPING_CACHE_KEY, json.dumps(payload).encode("utf-8"))


def _read_snapshot(client) -> dict:
    raw = client.get(VEHICLES_ALL_KEY)
    assert raw is not None, "vehicles:all SET expected but key absent"
    return json.loads(raw)


# --- 1. happy path --------------------------------------------------------


def test_happy_path_single_vehicle(fake_redis, patch_adapter, captured_group_sends):
    _seed_mapping(fake_redis, {"A-231": [_interval(1000, 99999, "29B")]})
    patch_adapter(fetch_return=[_make_vehicle("A-231", ts_ms=5000, speed=24.0)])

    result = fetch_iett_positions()
    snapshot = _read_snapshot(fake_redis)

    assert snapshot["type"] == "vehicles_all_update"
    assert snapshot["vehicle_count"] == 1
    assert snapshot["mapped_count"] == 1
    assert len(snapshot["vehicles"]) == 1
    assert snapshot["vehicles"][0]["id"] == "A-231"
    assert snapshot["vehicles"][0]["route_id"] == "29B"

    assert int(fake_redis.get(UNMAPPED_COUNT_KEY)) == 0
    assert fake_redis.get(LAST_FETCH_TS_KEY).endswith(b"Z")

    assert len(captured_group_sends) == 1
    group, message = captured_group_sends[0]
    assert group == VEHICLES_ALL_GROUP
    assert message["data"] == snapshot

    assert result["status"] == "ok"
    assert result["fetched"] == 1
    assert result["mapped_count"] == 1
    assert result["unmapped"] == 0


# --- 2. unmapped vehicle stays in payload with route_id=null --------------


def test_unmapped_vehicle_included_with_null_route_id(
    fake_redis, patch_adapter, captured_group_sends
):
    """UX pivot invariant: unmapped vehicles MUST appear in the snapshot
    so the frontend can render them as ham points (popup says 'hat
    bilinmiyor'). Pre-pivot the per-route fanout dropped them; vehicles:all
    keeps them with route_id=null."""
    _seed_mapping(fake_redis, {"A-231": [_interval(1000, 9999, "29B")]})
    patch_adapter(fetch_return=[
        _make_vehicle("A-231", ts_ms=5000),
        _make_vehicle("X-999", ts_ms=5000),  # not in mapping
    ])

    result = fetch_iett_positions()
    snapshot = _read_snapshot(fake_redis)

    by_id = {v["id"]: v for v in snapshot["vehicles"]}
    assert by_id["A-231"]["route_id"] == "29B"
    assert by_id["X-999"]["route_id"] is None

    assert snapshot["vehicle_count"] == 2
    assert snapshot["mapped_count"] == 1

    assert int(fake_redis.get(UNMAPPED_COUNT_KEY)) == 1
    assert result["unmapped"] == 1
    assert result["mapped_count"] == 1
    assert len(captured_group_sends) == 1


# --- 3. cache miss → still broadcasts, all unmapped -----------------------


def test_mapping_cache_miss_all_unmapped_still_broadcasts(
    fake_redis, patch_adapter, captured_group_sends, caplog
):
    """Cache miss no longer suppresses pub: snapshot fans out with every
    vehicle route_id=null. Frontend gets the raw fleet; admin sees
    unmapped_count blowing up (5f) and the WARNING log fires."""
    # Note: deliberately do NOT seed the mapping key.
    patch_adapter(fetch_return=[
        _make_vehicle("A-231"),
        _make_vehicle("B-100"),
        _make_vehicle("C-50"),
    ])

    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        result = fetch_iett_positions()

    snapshot = _read_snapshot(fake_redis)

    assert snapshot["vehicle_count"] == 3
    assert snapshot["mapped_count"] == 0
    assert all(v["route_id"] is None for v in snapshot["vehicles"])

    assert int(fake_redis.get(UNMAPPED_COUNT_KEY)) == 3
    assert result["unmapped"] == 3
    assert result["mapped_count"] == 0

    assert len(captured_group_sends) == 1
    assert captured_group_sends[0][0] == VEHICLES_ALL_GROUP

    miss_warnings = [
        r.getMessage() for r in caplog.records
        if r.levelno == logging.WARNING and "mapping cache miss" in r.getMessage()
    ]
    assert len(miss_warnings) == 1


# --- 4. adapter failure branches → graceful return, no side effects -------


def test_adapter_generic_exception_returns_error(
    fake_redis, patch_adapter, captured_group_sends, caplog
):
    _seed_mapping(fake_redis, {"A-231": [_interval(1000, 99999, "29B")]})
    patch_adapter(fetch_raises=RuntimeError("upstream exploded"))

    with caplog.at_level(logging.ERROR, logger=LOGGER_NAME):
        result = fetch_iett_positions()

    assert result["status"] == "error"
    assert result["error_type"] == "RuntimeError"
    assert "upstream exploded" in result["error"]

    assert fake_redis.exists(VEHICLES_ALL_KEY) == 0
    assert fake_redis.get(UNMAPPED_COUNT_KEY) is None
    assert captured_group_sends == []

    exc_records = [r for r in caplog.records if r.exc_info is not None]
    assert len(exc_records) >= 1


def test_adapter_rate_limit_violation_returns_error(
    fake_redis, patch_adapter, captured_group_sends, caplog
):
    _seed_mapping(fake_redis, {"A-231": [_interval(1000, 99999, "29B")]})
    patch_adapter(fetch_raises=IettRateLimitViolation("budget exhausted"))

    with caplog.at_level(logging.ERROR, logger=LOGGER_NAME):
        result = fetch_iett_positions()

    assert result["status"] == "error"
    assert result["error_type"] == "rate_limit_violation"
    assert "budget exhausted" in result["error"]

    assert fake_redis.exists(VEHICLES_ALL_KEY) == 0
    assert fake_redis.get(UNMAPPED_COUNT_KEY) is None
    assert captured_group_sends == []

    err_records = [
        r for r in caplog.records
        if r.levelno == logging.ERROR and "rate-limit violation" in r.getMessage()
    ]
    assert len(err_records) == 1


def test_adapter_http_error_returns_error(
    fake_redis, patch_adapter, captured_group_sends, caplog
):
    _seed_mapping(fake_redis, {"A-231": [_interval(1000, 99999, "29B")]})
    patch_adapter(fetch_raises=requests.HTTPError("502 Bad Gateway"))

    with caplog.at_level(logging.ERROR, logger=LOGGER_NAME):
        result = fetch_iett_positions()

    assert result["status"] == "error"
    assert result["error_type"] == "http_error"
    assert "502" in result["error"]

    assert fake_redis.exists(VEHICLES_ALL_KEY) == 0
    assert fake_redis.get(UNMAPPED_COUNT_KEY) is None
    assert captured_group_sends == []

    err_records = [
        r for r in caplog.records
        if r.levelno == logging.ERROR and "upstream HTTP error" in r.getMessage()
    ]
    assert len(err_records) == 1


# --- 5. empty fleet → still broadcasts a zero-payload heartbeat -----------


def test_empty_vehicle_list_still_broadcasts_zero_payload(
    fake_redis, patch_adapter, captured_group_sends
):
    """Frontend MUST receive an empty snapshot rather than nothing — else
    the last cached state on the client looks 'stale-but-recent'."""
    _seed_mapping(fake_redis, {"A-231": [_interval(1000, 99999, "29B")]})
    patch_adapter(fetch_return=[])

    result = fetch_iett_positions()
    snapshot = _read_snapshot(fake_redis)

    assert snapshot["vehicle_count"] == 0
    assert snapshot["mapped_count"] == 0
    assert snapshot["vehicles"] == []

    assert len(captured_group_sends) == 1
    assert captured_group_sends[0][1]["data"] == snapshot

    assert int(fake_redis.get(UNMAPPED_COUNT_KEY)) == 0
    assert result["fetched"] == 0
    assert result["unmapped"] == 0
    assert result["mapped_count"] == 0


# --- 6. payload format matches vehicles:all spec --------------------------


def test_payload_format_matches_vehicles_all_spec(
    fake_redis, patch_adapter, captured_group_sends
):
    _seed_mapping(fake_redis, {"A-231": [_interval(1000, 99999, "29B")]})
    patch_adapter(fetch_return=[
        _make_vehicle("A-231", ts_ms=5000, speed=24.0, bearing=None,
                      latitude=41.04885, longitude=29.10322),
    ])

    fetch_iett_positions()
    raw = fake_redis.get(VEHICLES_ALL_KEY)
    assert b'"bearing":null' in raw  # JSON null literal, not "None"

    snapshot = json.loads(raw)
    assert set(snapshot) == {
        "type", "timestamp", "vehicle_count", "mapped_count", "vehicles",
    }
    assert snapshot["type"] == "vehicles_all_update"
    assert snapshot["timestamp"].endswith("Z")
    datetime.fromisoformat(snapshot["timestamp"].replace("Z", "+00:00"))

    veh = snapshot["vehicles"][0]
    assert set(veh) == {"id", "lat", "lon", "bearing", "speed", "route_id"}
    assert veh["bearing"] is None
    assert veh["speed"] == 24.0
    assert veh["lat"] == 41.04885
    assert veh["lon"] == 29.10322
    assert veh["route_id"] == "29B"


# --- 7. SET vehicles:all + group_send both happen (atomic invariant) ------


def test_set_and_group_send_both_called(
    fake_redis, patch_adapter, captured_group_sends
):
    _seed_mapping(fake_redis, {"A-231": [_interval(1000, 99999, "29B")]})
    patch_adapter(fetch_return=[_make_vehicle("A-231")])

    fetch_iett_positions()

    # SET happened
    cached = fake_redis.get(VEHICLES_ALL_KEY)
    assert cached is not None

    ttl = fake_redis.ttl(VEHICLES_ALL_KEY)
    assert VEHICLES_CACHE_TTL_SECONDS - 5 <= ttl <= VEHICLES_CACHE_TTL_SECONDS

    # group_send happened, into the right group, with the same payload
    assert len(captured_group_sends) == 1
    group, message = captured_group_sends[0]
    assert group == VEHICLES_ALL_GROUP
    assert message["data"] == json.loads(cached)


# --- 8. mapped_count excludes unmapped (5 vehicles, 3 mapped) -------------


def test_mapped_count_excludes_unmapped(
    fake_redis, patch_adapter, captured_group_sends
):
    _seed_mapping(fake_redis, {
        "A-1": [_interval(1000, 99999, "29B")],
        "A-2": [_interval(1000, 99999, "29B")],
        "A-3": [_interval(1000, 99999, "34BZ")],
    })
    patch_adapter(fetch_return=[
        _make_vehicle("A-1"),
        _make_vehicle("A-2"),
        _make_vehicle("A-3"),
        _make_vehicle("X-1"),  # unmapped
        _make_vehicle("X-2"),  # unmapped
    ])

    result = fetch_iett_positions()
    snapshot = _read_snapshot(fake_redis)

    assert snapshot["vehicle_count"] == 5
    assert snapshot["mapped_count"] == 3
    assert result["mapped_count"] == 3
    assert result["unmapped"] == 2
    assert int(fake_redis.get(UNMAPPED_COUNT_KEY)) == 2


# --- 9. unmapped count overwrites previous tick (heartbeat semantics) -----


def test_unmapped_count_overwrites_previous_tick(fake_redis, patch_adapter):
    fake_redis.set(UNMAPPED_COUNT_KEY, 999)

    _seed_mapping(fake_redis, {"A-231": [_interval(1000, 99999, "29B")]})
    patch_adapter(fetch_return=[_make_vehicle("A-231")])

    fetch_iett_positions()

    assert int(fake_redis.get(UNMAPPED_COUNT_KEY)) == 0


# --- 10-11. Day-type mismatch counter (5i-iv, model-agnostic) -------------


def test_day_type_mismatch_increments_counter(fake_redis, patch_adapter):
    """Mapping snapshot_day_type='weekday' but vehicle is on a Saturday →
    sample-based mismatch detection fires INCR on the counter key."""
    sat_local = datetime(2026, 4, 25, 12, 0, 0, tzinfo=ISTANBUL_TZ)  # Saturday
    sat_ms = int(sat_local.timestamp() * 1000)
    vehicle = _make_vehicle("A-231", ts_ms=sat_ms)

    _seed_mapping(
        fake_redis,
        {"A-231": [_interval(0, 86399, "29B")]},
        snapshot_date="2026-04-22",  # Wednesday
        snapshot_day_type="weekday",
    )
    patch_adapter(fetch_return=[vehicle])

    fetch_iett_positions()

    assert int(fake_redis.get(DAY_TYPE_MISMATCH_COUNT_KEY)) == 1


def test_no_mismatch_does_not_increment_counter(fake_redis, patch_adapter):
    """Default _seed_mapping uses day_type='sunday' and 1970-01-01 maps
    to 'sunday' (Yılbaşı holiday → Sunday timetable per get_day_type) →
    no INCR."""
    _seed_mapping(fake_redis, {"A-231": [_interval(1000, 99999, "29B")]})
    patch_adapter(fetch_return=[_make_vehicle("A-231")])

    fetch_iett_positions()

    assert fake_redis.get(DAY_TYPE_MISMATCH_COUNT_KEY) is None
