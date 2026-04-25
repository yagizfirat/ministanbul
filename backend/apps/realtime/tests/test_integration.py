"""End-to-end integration tests for the realtime pipeline (Phase 2 Step 5g).

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
    fetch_iett_positions,
)

CASSETTE_DIR = Path(__file__).parent / "cassettes"
BIG_END_SEC = 86399  # 23:59:59 — covers any same-day wall-clock vehicle timestamp


# --- fixtures --------------------------------------------------------------


@pytest.fixture
def fake_redis(monkeypatch):
    """Shared FakeStrictRedis: the task client and the test subscriber
    both go through this instance so PUBLISH delivers to GET-readers."""
    client = fakeredis.FakeStrictRedis()
    monkeypatch.setattr(
        tasks_module.redis, "from_url",
        lambda *a, **kw: client,
    )
    return client


# --- helpers ---------------------------------------------------------------


def _patch_adapter_returning(monkeypatch, vehicles: list[VehiclePosition]) -> None:
    """Swap ``_make_adapter`` for a stub whose ``fetch`` returns ``vehicles``."""
    def _fetch():
        return vehicles
    adapter = SimpleNamespace(fetch=_fetch)
    monkeypatch.setattr(
        tasks_module, "_make_adapter", lambda redis_client: adapter,
    )


def _patch_adapter_raising(monkeypatch, exc: Exception) -> None:
    """Swap ``_make_adapter`` for a stub whose ``fetch`` raises ``exc``."""
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
    """Write mapping payload to ``iett:mapping:current`` (same shape as
    ``build_mapping`` produces post-5i-i: snapshot_date + snapshot_day_type
    + start_sec/end_sec)."""
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


def _subscribe(client, *channels) -> object:
    pubsub = client.pubsub()
    pubsub.subscribe(*channels)
    for _ in channels:
        ack = pubsub.get_message(timeout=1.0)
        assert ack is not None and ack["type"] == "subscribe"
    return pubsub


def _drain_messages(pubsub, expected_count: int, timeout: float = 1.0) -> list[dict]:
    out: list[dict] = []
    while len(out) < expected_count:
        msg = pubsub.get_message(timeout=timeout)
        if msg is None:
            break
        if msg.get("type") == "message":
            out.append(msg)
    return out


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


# --- 1. End-to-end with real fleet cassette ------------------------------


def test_end_to_end_chain_with_real_fleet_cassette(fake_redis, monkeypatch):
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

    # 4 → 29B, 3 → 34BZ, 1 → M2, last 4 → unmapped (no mapping entry).
    by_kapi: dict[str, list[dict]] = {}
    for kapi in kapis[0:4]:
        by_kapi[kapi] = [_interval(0, BIG_END_SEC, "29B")]
    for kapi in kapis[4:7]:
        by_kapi[kapi] = [_interval(0, BIG_END_SEC, "34BZ")]
    by_kapi[kapis[7]] = [_interval(0, BIG_END_SEC, "M2")]

    _seed_mapping(fake_redis, by_kapi)
    _patch_adapter_returning(monkeypatch, vehicles)

    pubsub = _subscribe(
        fake_redis,
        "vehicles:route:29B",
        "vehicles:route:34BZ",
        "vehicles:route:M2",
    )
    result = fetch_iett_positions()
    msgs = _drain_messages(pubsub, expected_count=3)

    by_route: dict[str, list] = {}
    for msg in msgs:
        payload = json.loads(msg["data"])
        by_route[payload["route_id"]] = payload["vehicles"]

    assert set(by_route) == {"29B", "34BZ", "M2"}
    assert len(by_route["29B"]) == 4
    assert len(by_route["34BZ"]) == 3
    assert len(by_route["M2"]) == 1

    # Cache (SET) matches the pub payload exactly for one channel.
    cached_29b = json.loads(fake_redis.get("vehicles:route:29B"))
    assert {v["id"] for v in cached_29b["vehicles"]} == {
        v["id"] for v in by_route["29B"]
    }

    # Counts + heartbeat written.
    expected_unmapped = len(vehicles) - 8
    assert int(fake_redis.get(UNMAPPED_COUNT_KEY)) == expected_unmapped
    last_fetch = fake_redis.get(LAST_FETCH_TS_KEY)
    assert last_fetch is not None and last_fetch.endswith(b"Z")

    assert result["status"] == "ok"
    assert result["fetched"] == len(vehicles)
    assert result["unmapped"] == expected_unmapped
    assert result["routes"] == 3


# --- 2. Stale cache survives an adapter failure --------------------------


def test_stale_cache_survives_adapter_failure(fake_redis, monkeypatch):
    by_kapi = {"A-231": [_interval(0, BIG_END_SEC, "29B")]}
    _seed_mapping(fake_redis, by_kapi)

    with freeze_time("2026-04-25 12:00:00") as frozen:
        # --- Tick 1: happy path → SET vehicles:route:29B with TTL=120 ---
        ts_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
        _patch_adapter_returning(
            monkeypatch, [_make_synthetic_vehicle("A-231", ts_ms)],
        )
        fetch_iett_positions()

        cached_t1 = fake_redis.get("vehicles:route:29B")
        assert cached_t1 is not None
        ttl_t1 = fake_redis.ttl("vehicles:route:29B")
        assert 118 <= ttl_t1 <= 120

        # --- 30 seconds elapse on the frozen clock ---
        frozen.tick(delta=timedelta(seconds=30))

        # --- Tick 2: adapter explodes → task returns error, no Redis writes ---
        _patch_adapter_raising(monkeypatch, RuntimeError("upstream down"))
        result = fetch_iett_positions()

        assert result["status"] == "error"
        assert result["error_type"] == "RuntimeError"

        # Stale snapshot intact: not overwritten, not deleted.
        cached_t2 = fake_redis.get("vehicles:route:29B")
        assert cached_t2 == cached_t1

        # TTL shrank by ~30 seconds. Tolerate ±2 s for any fakeredis drift.
        ttl_t2 = fake_redis.ttl("vehicles:route:29B")
        assert 88 <= ttl_t2 <= 90


# --- 3. Mapping miss → seed → recovery -----------------------------------


def test_mapping_miss_then_present_recovery(fake_redis, monkeypatch):
    ts_ms = 5000
    vehicles = [
        _make_synthetic_vehicle("A-231", ts_ms),
        _make_synthetic_vehicle("B-100", ts_ms),
        _make_synthetic_vehicle("C-50", ts_ms),
    ]
    _patch_adapter_returning(monkeypatch, vehicles)

    # --- Tick 1: no mapping seeded → all unmapped, no pub ---
    pubsub_t1 = _subscribe(fake_redis, "vehicles:route:29B")
    result_t1 = fetch_iett_positions()
    msgs_t1 = _drain_messages(pubsub_t1, expected_count=1, timeout=0.2)

    assert msgs_t1 == []
    assert fake_redis.keys("vehicles:route:*") == []
    assert int(fake_redis.get(UNMAPPED_COUNT_KEY)) == 3
    assert result_t1["routes"] == 0
    assert result_t1["unmapped"] == 3

    # --- Mapping seeded between ticks (synthetic, not via refresh task) ---
    _seed_mapping(fake_redis, {
        "A-231": [_interval(0, BIG_END_SEC, "29B")],
        "B-100": [_interval(0, BIG_END_SEC, "29B")],
        "C-50":  [_interval(0, BIG_END_SEC, "34BZ")],
    })

    # --- Tick 2: same adapter snapshot, mapping now present → pub fires ---
    pubsub_t2 = _subscribe(
        fake_redis, "vehicles:route:29B", "vehicles:route:34BZ",
    )
    result_t2 = fetch_iett_positions()
    msgs_t2 = _drain_messages(pubsub_t2, expected_count=2)

    assert len(msgs_t2) == 2
    routes_seen = {json.loads(m["data"])["route_id"] for m in msgs_t2}
    assert routes_seen == {"29B", "34BZ"}

    assert int(fake_redis.get(UNMAPPED_COUNT_KEY)) == 0
    assert result_t2["fetched"] == 3
    assert result_t2["unmapped"] == 0
    assert result_t2["routes"] == 2


# --- 4. Same KapiNo lands on different routes across ticks ---------------


def test_same_kapi_different_routes_across_ticks(fake_redis, monkeypatch):
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

    pubsub = _subscribe(
        fake_redis, "vehicles:route:29B", "vehicles:route:15B",
    )

    # --- Tick 1: morning timestamp → 29B interval ---
    _patch_adapter_returning(
        monkeypatch, [_make_synthetic_vehicle("A-231", morning_ms)],
    )
    fetch_iett_positions()
    msgs_t1 = _drain_messages(pubsub, expected_count=1)

    assert len(msgs_t1) == 1
    payload_t1 = json.loads(msgs_t1[0]["data"])
    assert payload_t1["route_id"] == "29B"
    assert payload_t1["vehicles"][0]["id"] == "A-231"

    # --- Tick 2: afternoon timestamp → 15B interval (later-starting wins) ---
    _patch_adapter_returning(
        monkeypatch, [_make_synthetic_vehicle("A-231", afternoon_ms)],
    )
    fetch_iett_positions()
    msgs_t2 = _drain_messages(pubsub, expected_count=1)

    assert len(msgs_t2) == 1
    payload_t2 = json.loads(msgs_t2[0]["data"])
    assert payload_t2["route_id"] == "15B"
    assert payload_t2["vehicles"][0]["id"] == "A-231"

    # Both cache snapshots remain (TTL not breached during the test).
    assert fake_redis.get("vehicles:route:29B") is not None
    assert fake_redis.get("vehicles:route:15B") is not None
