"""End-to-end integration tests for the realtime pipeline (Phase 2 Step 5g,
revised in Phase 3 Step 6c for the vehicles:all model).

Each unit test covers a single piece in isolation; this file exercises
the full chain over a single fakeredis instance, with the same monkey-
patch shape used by Celery workers in production.

Cassette + synthetic mapping mix:
- The fleet adapter is exercised through its real parser
  (cassette → ``_parse_fleet_response`` → ``list[VehiclePosition]``);
  ``adapter.fetch`` is then stubbed to return that list, so HTTP / lock
  / rate-limit are bypassed but the wire-shape parsing is honest.
- Mapping payloads are written directly to Redis under
  ``iett:mapping:current`` in the same shape ``build_mapping`` produces
  — no need to invoke the refresh task; that path is already covered
  in ``test_refresh_task.py``.
- ``channel_layer.group_send`` is replaced by an autouse fixture that
  captures broadcasts into a Python list — no Memurai db=1 traffic.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import fakeredis
import pytest
from freezegun import freeze_time

from apps.realtime import tasks as tasks_module
from apps.realtime.adapters.iett_soap import _parse_fleet_response
from apps.realtime.schemas import VehiclePosition
from apps.realtime.tasks import (
    LAST_FETCH_TS_KEY,
    MAPPING_CACHE_KEY,
    UNMAPPED_COUNT_KEY,
    VEHICLES_ALL_GROUP,
    VEHICLES_ALL_KEY,
    fetch_iett_positions,
)

CASSETTE_DIR = Path(__file__).parent / "cassettes"
BIG_END_SEC = 86399  # 23:59:59 — covers any same-day wall-clock vehicle timestamp


# --- fixtures --------------------------------------------------------------


@pytest.fixture
def fake_redis(monkeypatch):
    """Shared FakeStrictRedis: the task client and the test reader both
    go through this instance so SET inside the task is observable."""
    client = fakeredis.FakeStrictRedis()
    monkeypatch.setattr(
        tasks_module.redis, "from_url",
        lambda *a, **kw: client,
    )
    return client


@pytest.fixture(autouse=True)
def captured_group_sends(monkeypatch):
    """Capture ``channel_layer.group_send`` into a list. Same pattern as
    test_fetch_task — autouse so the real RedisChannelLayer never wakes."""
    sent: list[tuple[str, dict]] = []

    async def fake_group_send(group, message):
        sent.append((group, message))

    layer = SimpleNamespace(group_send=fake_group_send)
    monkeypatch.setattr(
        tasks_module, "get_channel_layer", lambda: layer,
    )
    return sent


# --- helpers ---------------------------------------------------------------


def _patch_adapter_returning(monkeypatch, vehicles: list[VehiclePosition]) -> None:
    def _fetch():
        return vehicles
    adapter = SimpleNamespace(fetch=_fetch)
    monkeypatch.setattr(
        tasks_module, "_make_adapter", lambda redis_client: adapter,
    )


def _patch_adapter_raising(monkeypatch, exc: Exception) -> None:
    def _fetch():
        raise exc
    adapter = SimpleNamespace(fetch=_fetch)
    monkeypatch.setattr(
        tasks_module, "_make_adapter", lambda redis_client: adapter,
    )


def _interval(start_sec: int, end_sec: int, hat: str) -> dict:
    return {
        "start_sec": start_sec,
        "end_sec": end_sec,
        "hat": hat,
        "guzergah": f"{hat}_G_D0",
    }


def _seed_mapping(redis_client, by_kapi: dict[str, list[dict]]) -> None:
    """Write mapping payload to ``iett:mapping:current`` (post-5i-i shape:
    snapshot_date + snapshot_day_type + start_sec/end_sec)."""
    active = sorted({iv["hat"] for ivs in by_kapi.values() for iv in ivs})
    payload = {
        "snapshot_date": "2026-04-25",   # Saturday (matches cassette ts day-type)
        "snapshot_day_type": "saturday",  # cassette vehicles fall in 15:50-20:29 IST
        "by_kapi": by_kapi,
        "active_routes": active,
        "routes_by_mode": {"metrobus": [], "bus": active},
    }
    redis_client.set(MAPPING_CACHE_KEY, json.dumps(payload).encode("utf-8"))


def _sec(h: int, m: int = 0, s: int = 0) -> int:
    """Wall-clock seconds since midnight."""
    return h * 3600 + m * 60 + s


def _ms_from_iso(iso: str) -> int:
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp() * 1000)


def _make_synthetic_vehicle(
    vehicle_id: str,
    ts_ms: int,
    *,
    latitude: float = 41.0,
    longitude: float = 29.0,
) -> VehiclePosition:
    return VehiclePosition(
        vehicle_id=vehicle_id,
        latitude=latitude,
        longitude=longitude,
        timestamp=datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc),
        source="iett-soap",
        mode="bus",
    )


def _read_snapshot(redis_client) -> dict:
    raw = redis_client.get(VEHICLES_ALL_KEY)
    assert raw is not None, "vehicles:all SET expected but key absent"
    return json.loads(raw)


# --- 1. End-to-end with real fleet cassette ------------------------------


def test_end_to_end_chain_with_real_fleet_cassette(
    fake_redis, monkeypatch, captured_group_sends
):
    cassette = (CASSETTE_DIR / "filo_fetch_ok.xml").read_text(encoding="utf-8")
    parsed_at = datetime(2026, 4, 25, 12, 0, 0, tzinfo=timezone.utc)
    vehicles = _parse_fleet_response(cassette, at=parsed_at)

    # Need at least 8 vehicles for the 4+3+1 route assignment below.
    # Anything beyond 8 stays unmapped — math derives from len(vehicles).
    assert len(vehicles) >= 8, (
        f"cassette parser yielded {len(vehicles)}, need at least 8 "
        "for the 4+3+1 route assignment"
    )

    # Sort by KapiNo so the mapping assignment is stable across runs.
    sorted_vehicles = sorted(vehicles, key=lambda v: v.vehicle_id)
    kapis = [v.vehicle_id for v in sorted_vehicles]

    # 4 → 29B, 3 → 34BZ, 1 → M2, last len-8 → unmapped (no mapping entry).
    by_kapi: dict[str, list[dict]] = {}
    for kapi in kapis[0:4]:
        by_kapi[kapi] = [_interval(0, BIG_END_SEC, "29B")]
    for kapi in kapis[4:7]:
        by_kapi[kapi] = [_interval(0, BIG_END_SEC, "34BZ")]
    by_kapi[kapis[7]] = [_interval(0, BIG_END_SEC, "M2")]

    _seed_mapping(fake_redis, by_kapi)
    _patch_adapter_returning(monkeypatch, vehicles)

    result = fetch_iett_positions()
    snapshot = _read_snapshot(fake_redis)

    # Every fleet vehicle present in the single fleet-wide payload.
    assert snapshot["vehicle_count"] == len(vehicles)
    assert len(snapshot["vehicles"]) == len(vehicles)

    # Per-route distribution recovered via Counter on route_id (mapped_count
    # == 8, the routes covered by mapping; the rest carry route_id=null).
    by_route: dict = {}
    for v in snapshot["vehicles"]:
        by_route.setdefault(v["route_id"], []).append(v["id"])

    assert {r for r in by_route if r is not None} == {"29B", "34BZ", "M2"}
    assert len(by_route["29B"]) == 4
    assert len(by_route["34BZ"]) == 3
    assert len(by_route["M2"]) == 1

    expected_unmapped = len(vehicles) - 8
    assert len(by_route.get(None, [])) == expected_unmapped
    assert snapshot["mapped_count"] == 8

    # Single broadcast, mirrors the SET payload byte-for-byte.
    assert len(captured_group_sends) == 1
    group, message = captured_group_sends[0]
    assert group == VEHICLES_ALL_GROUP
    assert message["data"] == snapshot

    # Counts + heartbeat written.
    assert int(fake_redis.get(UNMAPPED_COUNT_KEY)) == expected_unmapped
    last_fetch = fake_redis.get(LAST_FETCH_TS_KEY)
    assert last_fetch is not None and last_fetch.endswith(b"Z")

    assert result["status"] == "ok"
    assert result["fetched"] == len(vehicles)
    assert result["unmapped"] == expected_unmapped
    assert result["mapped_count"] == 8


# --- 2. Stale cache survives an adapter failure --------------------------


def test_stale_cache_survives_adapter_failure(
    fake_redis, monkeypatch, captured_group_sends
):
    by_kapi = {"A-231": [_interval(0, BIG_END_SEC, "29B")]}
    _seed_mapping(fake_redis, by_kapi)

    with freeze_time("2026-04-25 12:00:00") as frozen:
        # --- Tick 1: happy path → SET vehicles:all with TTL=120 ---
        ts_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
        _patch_adapter_returning(
            monkeypatch, [_make_synthetic_vehicle("A-231", ts_ms)],
        )
        fetch_iett_positions()

        cached_t1 = fake_redis.get(VEHICLES_ALL_KEY)
        assert cached_t1 is not None
        ttl_t1 = fake_redis.ttl(VEHICLES_ALL_KEY)
        assert 118 <= ttl_t1 <= 120
        assert len(captured_group_sends) == 1

        # --- 30 seconds elapse on the frozen clock ---
        frozen.tick(delta=timedelta(seconds=30))

        # --- Tick 2: adapter explodes → task returns error, no Redis writes ---
        _patch_adapter_raising(monkeypatch, RuntimeError("upstream down"))
        result = fetch_iett_positions()

        assert result["status"] == "error"
        assert result["error_type"] == "RuntimeError"

        # Stale snapshot intact: not overwritten, not deleted.
        cached_t2 = fake_redis.get(VEHICLES_ALL_KEY)
        assert cached_t2 == cached_t1

        # No second broadcast — adapter failure short-circuits.
        assert len(captured_group_sends) == 1

        # TTL shrank by ~30 seconds. Tolerate ±2 s for any fakeredis drift.
        ttl_t2 = fake_redis.ttl(VEHICLES_ALL_KEY)
        assert 88 <= ttl_t2 <= 90


# --- 3. Mapping miss → seed → recovery -----------------------------------


def test_mapping_miss_then_present_recovery(
    fake_redis, monkeypatch, captured_group_sends
):
    """Two-tick recovery — same adapter snapshot, different mapping
    state. Tick 1: cache miss but broadcast still fires (UX pivot); all
    vehicles route_id=null. Tick 2: mapping seeded, same vehicles now
    carry route_id from the mapping."""
    ts_ms = 5000
    vehicles = [
        _make_synthetic_vehicle("A-231", ts_ms),
        _make_synthetic_vehicle("B-100", ts_ms),
        _make_synthetic_vehicle("C-50", ts_ms),
    ]
    _patch_adapter_returning(monkeypatch, vehicles)

    # --- Tick 1: no mapping seeded → broadcast still fires, all unmapped ---
    result_t1 = fetch_iett_positions()
    snapshot_t1 = _read_snapshot(fake_redis)

    assert snapshot_t1["vehicle_count"] == 3
    assert snapshot_t1["mapped_count"] == 0
    assert all(v["route_id"] is None for v in snapshot_t1["vehicles"])

    assert len(captured_group_sends) == 1
    assert int(fake_redis.get(UNMAPPED_COUNT_KEY)) == 3
    assert result_t1["mapped_count"] == 0
    assert result_t1["unmapped"] == 3

    # --- Mapping seeded between ticks (synthetic, not via refresh task) ---
    _seed_mapping(fake_redis, {
        "A-231": [_interval(0, BIG_END_SEC, "29B")],
        "B-100": [_interval(0, BIG_END_SEC, "29B")],
        "C-50":  [_interval(0, BIG_END_SEC, "34BZ")],
    })

    # --- Tick 2: same adapter snapshot, mapping now present → route_id dolu --
    result_t2 = fetch_iett_positions()
    snapshot_t2 = _read_snapshot(fake_redis)

    by_kapi = {v["id"]: v["route_id"] for v in snapshot_t2["vehicles"]}
    assert by_kapi == {"A-231": "29B", "B-100": "29B", "C-50": "34BZ"}
    assert snapshot_t2["mapped_count"] == 3

    # Second broadcast fired (total = 2).
    assert len(captured_group_sends) == 2
    assert int(fake_redis.get(UNMAPPED_COUNT_KEY)) == 0
    assert result_t2["fetched"] == 3
    assert result_t2["unmapped"] == 0
    assert result_t2["mapped_count"] == 3


# --- 4. Same KapiNo lands on different routes across ticks ---------------


def test_same_kapi_different_routes_across_ticks(
    fake_redis, monkeypatch, captured_group_sends
):
    """Time-aware enrichment invariant: same KapiNo, two ticks, two
    intervals → vehicle.route_id flips. Single vehicles:all key, content
    differs across ticks. Bisect picks the later-starting interval."""
    # IST wall-clock: morning 08:00, afternoon 16:00. Use +03:00 ISO so the
    # resulting epoch ms, after astimezone(IST) inside enrich, lands at the
    # right wall-clock seconds (8*3600 / 16*3600).
    morning_ms = _ms_from_iso("2026-04-25T08:00:00+03:00")
    afternoon_ms = _ms_from_iso("2026-04-25T16:00:00+03:00")

    # Mapping intervals in IST wall-clock seconds:
    #   06:00-14:00 (21600-50400) → 29B (sabah)
    #   14:00-22:00 (50400-79200) → 15B (öğleden sonra)
    _seed_mapping(fake_redis, {
        "A-231": [
            {"start_sec": _sec(6),  "end_sec": _sec(14),
             "hat": "29B", "guzergah": "29B_G_D0"},
            {"start_sec": _sec(14), "end_sec": _sec(22),
             "hat": "15B", "guzergah": "15B_G_D0"},
        ]
    })

    # --- Tick 1: morning timestamp → 29B interval ---
    _patch_adapter_returning(
        monkeypatch, [_make_synthetic_vehicle("A-231", morning_ms)],
    )
    fetch_iett_positions()
    snapshot_t1 = _read_snapshot(fake_redis)

    assert len(snapshot_t1["vehicles"]) == 1
    assert snapshot_t1["vehicles"][0]["id"] == "A-231"
    assert snapshot_t1["vehicles"][0]["route_id"] == "29B"

    # --- Tick 2: afternoon timestamp → 15B interval (later-starting wins) ---
    _patch_adapter_returning(
        monkeypatch, [_make_synthetic_vehicle("A-231", afternoon_ms)],
    )
    fetch_iett_positions()
    snapshot_t2 = _read_snapshot(fake_redis)

    # Same key, content overwritten — route_id flipped on the same kapı.
    assert len(snapshot_t2["vehicles"]) == 1
    assert snapshot_t2["vehicles"][0]["id"] == "A-231"
    assert snapshot_t2["vehicles"][0]["route_id"] == "15B"

    # Two broadcasts fired (one per tick), each with the tick's payload.
    assert len(captured_group_sends) == 2
    assert captured_group_sends[0][1]["data"]["vehicles"][0]["route_id"] == "29B"
    assert captured_group_sends[1][1]["data"]["vehicles"][0]["route_id"] == "15B"
