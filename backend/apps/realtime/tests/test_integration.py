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
import fakeredis.aioredis
import numpy as np
import pytest
from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator
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
from apps.realtime.tests._helpers import EXPECTED_PK_FOR_HAT

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


@pytest.fixture
def captured_group_sends(monkeypatch):
    """Capture ``channel_layer.group_send`` into a list. Same pattern as
    test_fetch_task. Opt-in (NOT autouse): the broadcast-reaches-consumer
    test wants the real InMemoryChannelLayer wired up, not this stub."""
    sent: list[tuple[str, dict]] = []

    async def fake_group_send(group, message):
        sent.append((group, message))

    layer = SimpleNamespace(group_send=fake_group_send)
    monkeypatch.setattr(
        tasks_module, "get_channel_layer", lambda: layer,
    )
    return sent


class _PermissiveCache(dict):
    """Cache.get her key için non-None dummy ndarray döndürür —
    tasks.py'daki ``shape_arr is None`` defansif dalı tetiklenmez,
    böylece spatial filter sırf is_vehicle_near_route sözleşmesine
    bağlı kalır."""

    _DUMMY = np.array([[0.0, 0.0]])

    def get(self, key, default=None):
        return self._DUMMY


@pytest.fixture(autouse=True)
def _permissive_spatial_cache(monkeypatch):
    """Mevcut testler spatial check'e karşı duyarsız — her vehicle
    her route'a "yakın" sayılır. Spatial-specific testler bu fixture'ı
    override eder. DB hit (build_route_shape_cache) hiç tetiklenmez."""
    monkeypatch.setattr(
        tasks_module, "is_vehicle_near_route",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(
        tasks_module, "get_route_shape_cache",
        lambda: _PermissiveCache(),
    )


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
    snapshot_date + snapshot_day_type + start_sec/end_sec).

    Yol B: ``route_id_by_short_name`` is auto-derived from the SHATKODU
    set via ``EXPECTED_PK_FOR_HAT``. M2 (a public-feed metro short_name
    that lies outside production's IETT bus β-filter) is included in the
    helper dict so end-to-end tests can simulate a mixed fleet.
    """
    active = sorted({iv["hat"] for ivs in by_kapi.values() for iv in ivs})
    pk_index = {sn: EXPECTED_PK_FOR_HAT[sn] for sn in active if sn in EXPECTED_PK_FOR_HAT}
    payload = {
        "snapshot_date": "2026-04-25",   # Saturday (matches cassette ts day-type)
        "snapshot_day_type": "saturday",  # cassette vehicles fall in 15:50-20:29 IST
        "by_kapi": by_kapi,
        "active_routes": active,
        "routes_by_mode": {"metrobus": [], "bus": active},
        "route_id_by_short_name": pk_index,
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


def _rest_get_vehicles_live():
    """Sync helper: Django test Client ile /api/vehicles/live/ GET."""
    from django.test import Client
    return Client().get("/api/vehicles/live/")


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

    expected_route_pks = {
        EXPECTED_PK_FOR_HAT["29B"],
        EXPECTED_PK_FOR_HAT["34BZ"],
        EXPECTED_PK_FOR_HAT["M2"],
    }
    assert {r for r in by_route if r is not None} == expected_route_pks
    assert len(by_route[EXPECTED_PK_FOR_HAT["29B"]]) == 4
    assert len(by_route[EXPECTED_PK_FOR_HAT["34BZ"]]) == 3
    assert len(by_route[EXPECTED_PK_FOR_HAT["M2"]]) == 1

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
    assert by_kapi == {
        "A-231": EXPECTED_PK_FOR_HAT["29B"],
        "B-100": EXPECTED_PK_FOR_HAT["29B"],
        "C-50": EXPECTED_PK_FOR_HAT["34BZ"],
    }
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
    assert snapshot_t1["vehicles"][0]["route_id"] == EXPECTED_PK_FOR_HAT["29B"]

    # --- Tick 2: afternoon timestamp → 15B interval (later-starting wins) ---
    _patch_adapter_returning(
        monkeypatch, [_make_synthetic_vehicle("A-231", afternoon_ms)],
    )
    fetch_iett_positions()
    snapshot_t2 = _read_snapshot(fake_redis)

    # Same key, content overwritten — route_id flipped on the same kapı.
    assert len(snapshot_t2["vehicles"]) == 1
    assert snapshot_t2["vehicles"][0]["id"] == "A-231"
    assert snapshot_t2["vehicles"][0]["route_id"] == EXPECTED_PK_FOR_HAT["15B"]

    # Two broadcasts fired (one per tick), each with the tick's payload.
    assert len(captured_group_sends) == 2
    assert (
        captured_group_sends[0][1]["data"]["vehicles"][0]["route_id"]
        == EXPECTED_PK_FOR_HAT["29B"]
    )
    assert (
        captured_group_sends[1][1]["data"]["vehicles"][0]["route_id"]
        == EXPECTED_PK_FOR_HAT["15B"]
    )


# --- 5. fetch task → consumer end-to-end (real InMemoryChannelLayer) ------
#
# Bu test captured_group_sends fixture'ını ALMAZ — gerçek
# channel_layer.group_send → InMemoryChannelLayer → consumer akışını
# doğrular. Pipeline-to-consumer kontratı uçtan-uca.


@pytest.fixture
def in_memory_channel_layer(settings):
    """Override RedisChannelLayer with InMemory for in-process group
    dispatch. test_consumer_vehicles ile simetrik."""
    settings.CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        },
    }


@pytest.fixture
def fake_async_redis(monkeypatch):
    """Mock the consumer's aioredis.from_url. Separate physical instance
    from the sync fake_redis used by the fetch task — the test exercises
    the broadcast path, not initial-snapshot delivery (vehicles:all
    snapshot landed on the sync fake; consumer GET on the async fake
    returns None, which is exactly the L4.B silent-wait we want here)."""
    client = fakeredis.aioredis.FakeRedis()
    monkeypatch.setattr(
        "apps.realtime.consumers.aioredis.from_url",
        lambda *a, **kw: client,
    )
    return client


@pytest.mark.asyncio
async def test_fetch_task_broadcast_reaches_websocket_consumer(
    fake_redis, monkeypatch, in_memory_channel_layer, fake_async_redis,
):
    cassette = (CASSETTE_DIR / "filo_fetch_ok.xml").read_text(encoding="utf-8")
    parsed_at = datetime(2026, 4, 25, 12, 0, 0, tzinfo=timezone.utc)
    vehicles = _parse_fleet_response(cassette, at=parsed_at)
    assert len(vehicles) >= 8

    sorted_vehicles = sorted(vehicles, key=lambda v: v.vehicle_id)
    kapis = [v.vehicle_id for v in sorted_vehicles]

    by_kapi: dict[str, list[dict]] = {}
    for kapi in kapis[0:4]:
        by_kapi[kapi] = [_interval(0, BIG_END_SEC, "29B")]
    for kapi in kapis[4:7]:
        by_kapi[kapi] = [_interval(0, BIG_END_SEC, "34BZ")]
    by_kapi[kapis[7]] = [_interval(0, BIG_END_SEC, "M2")]

    _seed_mapping(fake_redis, by_kapi)
    _patch_adapter_returning(monkeypatch, vehicles)

    # Connect first — vehicles:all not seeded on the async fake, so the
    # consumer's initial snapshot read returns None (L4.B silent wait).
    # The first message the client gets WILL be the broadcast from the
    # fetch task call below.
    from config.asgi import application
    communicator = WebsocketCommunicator(application, "/ws/vehicles/")
    communicator.scope["client"] = ("127.0.0.1", 12345)
    connected, _ = await communicator.connect()
    assert connected is True

    # fetch_iett_positions is sync (Celery task) — run it in a worker
    # thread so the asyncio loop driving the consumer keeps spinning.
    # Inside the task, async_to_sync(group_send) dispatches back into
    # the same in-memory channel layer the consumer joined.
    result = await sync_to_async(fetch_iett_positions)()
    assert result["status"] == "ok"

    msg = await communicator.receive_json_from()
    assert msg["type"] == "vehicles_all_update"
    assert msg["vehicle_count"] == len(vehicles)
    assert msg["mapped_count"] == 8

    by_route: dict = {}
    for v in msg["vehicles"]:
        by_route.setdefault(v["route_id"], []).append(v["id"])
    expected_route_pks = {
        EXPECTED_PK_FOR_HAT["29B"],
        EXPECTED_PK_FOR_HAT["34BZ"],
        EXPECTED_PK_FOR_HAT["M2"],
    }
    assert {r for r in by_route if r is not None} == expected_route_pks
    assert len(by_route[EXPECTED_PK_FOR_HAT["29B"]]) == 4
    assert len(by_route[EXPECTED_PK_FOR_HAT["34BZ"]]) == 3
    assert len(by_route[EXPECTED_PK_FOR_HAT["M2"]]) == 1
    assert len(by_route.get(None, [])) == len(vehicles) - 8

    await communicator.disconnect()


# --- 6. REST + WebSocket serve identical payloads -------------------------


@pytest.mark.asyncio
async def test_rest_and_websocket_serve_identical_payload(
    fake_redis, monkeypatch, in_memory_channel_layer, fake_async_redis,
    captured_group_sends,
):
    """REST endpoint ve WebSocket consumer aynı vehicles:all
    snapshot'ını byte-level identical sunar. Fetch task tek payload
    yazar (6c-i K1.A), iki tüketici aynı kaynaktan okur."""
    cassette = (CASSETTE_DIR / "filo_fetch_ok.xml").read_text(encoding="utf-8")
    parsed_at = datetime(2026, 4, 25, 12, 0, 0, tzinfo=timezone.utc)
    vehicles = _parse_fleet_response(cassette, at=parsed_at)
    assert len(vehicles) >= 8

    sorted_vehicles = sorted(vehicles, key=lambda v: v.vehicle_id)
    kapis = [v.vehicle_id for v in sorted_vehicles]
    by_kapi: dict[str, list[dict]] = {}
    for kapi in kapis[0:4]:
        by_kapi[kapi] = [_interval(0, BIG_END_SEC, "29B")]

    _seed_mapping(fake_redis, by_kapi)
    _patch_adapter_returning(monkeypatch, vehicles)

    # Pipeline tetikle: vehicles:all SET + group_send
    result = await sync_to_async(fetch_iett_positions)()
    assert result["status"] == "ok"

    # WebSocket bağlantısı aç (initial snapshot fake_async_redis'te yok,
    # L4.B silent wait; ama bağlantı kurulmuş olmalı). Test broadcast'i
    # captured_group_sends'ten alır — captured_group_sends fake group_send
    # SimpleNamespace üzerinden fetch task çağrısını yakalar; in_memory
    # layer ayrı dispatch path'tir, bu test'te broadcast oraya gitmez.
    from config.asgi import application
    communicator = WebsocketCommunicator(application, "/ws/vehicles/")
    communicator.scope["client"] = ("127.0.0.1", 12345)
    connected, _ = await communicator.connect()
    assert connected is True

    assert len(captured_group_sends) == 1
    ws_payload_from_broadcast = captured_group_sends[0][1]["data"]

    await communicator.disconnect()

    # REST'ten al
    rest_response = await sync_to_async(_rest_get_vehicles_live)()
    rest_payload = rest_response.json()

    # Broadcast (group_send'in data'sı) ile REST identical olmalı
    assert ws_payload_from_broadcast == rest_payload, (
        "WebSocket broadcast payload != REST endpoint response — "
        "iki tüketici aynı snapshot'ı farklı şekilde alıyor."
    )

    # Redis SET payload ile karşılaştır (kaynak)
    raw = fake_redis.get(VEHICLES_ALL_KEY)
    assert raw is not None
    set_payload = json.loads(raw)
    assert set_payload == rest_payload, (
        "vehicles:all SET payload != REST response — REST endpoint "
        "Redis'i doğru okumuyor."
    )


# --- 7. Pipeline writes identical payload to SET and broadcast ------------


def test_fetch_task_payload_identical_in_set_and_broadcast(
    fake_redis, monkeypatch, captured_group_sends,
):
    """Pipeline 6c-i K1.A kararı: tek payload nesnesi hem
    vehicles:all'a SET hem channel_layer.group_send'e gönderilir.
    İki yere ayrı serialize/deserialize cycle olmamalı, byte-level
    identical olmalı."""
    cassette = (CASSETTE_DIR / "filo_fetch_ok.xml").read_text(encoding="utf-8")
    parsed_at = datetime(2026, 4, 25, 12, 0, 0, tzinfo=timezone.utc)
    vehicles = _parse_fleet_response(cassette, at=parsed_at)
    assert len(vehicles) >= 8

    by_kapi = {vehicles[0].vehicle_id: [_interval(0, BIG_END_SEC, "29B")]}
    _seed_mapping(fake_redis, by_kapi)
    _patch_adapter_returning(monkeypatch, vehicles)

    fetch_iett_positions()

    # SET payload (Redis'ten oku)
    raw = fake_redis.get(VEHICLES_ALL_KEY)
    assert raw is not None
    set_payload = json.loads(raw)

    # Broadcast payload (captured group_send'ten oku)
    assert len(captured_group_sends) == 1
    broadcast_payload = captured_group_sends[0][1]["data"]

    # İkisi tam identical
    assert set_payload == broadcast_payload, (
        "SET payload != broadcast payload — fetch task ayrı serialize "
        "cycle yapıyor (K1.A 'tek payload' kararı ihlali)."
    )
