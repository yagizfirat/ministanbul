"""Tests for VehicleAllConsumer (Faz 3 Adım 6d-ii).

Async testler: WebsocketCommunicator in-process — gerçek Daphne /
network yok. Channels layer InMemoryChannelLayer ile override; group
broadcast'leri direkt asyncio kuyruğunda akar. Async Redis trafiği
fakeredis.aioredis üzerinden, hem REDIS_URL (initial snapshot) hem
CHANNELS_REDIS_URL (IP counter) aynı fake instance'a düşer — test
izolasyonu için yeterli (gerçek db ayrımını test etmiyoruz, davranış
test ediyoruz).
"""
from __future__ import annotations

import json
import logging

import fakeredis.aioredis
import pytest
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator

from apps.realtime.tasks import VEHICLES_ALL_GROUP, VEHICLES_ALL_KEY

LOGGER_NAME = "apps.realtime.consumers"


# --- fixtures --------------------------------------------------------------


@pytest.fixture(autouse=True)
def in_memory_channel_layer(settings):
    """Override the project's RedisChannelLayer with InMemory for the
    duration of each test — group_send stays in-process, no Memurai db=1
    traffic, no cross-test bleed."""
    settings.CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        },
    }


@pytest.fixture
def fake_async_redis(monkeypatch):
    """Single FakeRedis async instance shared between the consumer's
    REDIS_URL and CHANNELS_REDIS_URL clients. Behavior under test is
    SET/GET/INCR/DECR/EXPIRE — not the db split."""
    client = fakeredis.aioredis.FakeRedis()

    def _from_url(*args, **kwargs):
        return client

    monkeypatch.setattr(
        "apps.realtime.consumers.aioredis.from_url", _from_url,
    )
    return client


# --- helpers ---------------------------------------------------------------


def _make_communicator():
    # Importing application inside the helper avoids module import at
    # collection time (Django settings might not be ready yet under
    # some pytest-django interactions). WebsocketCommunicator's default
    # scope omits "client" entirely, so we set it explicitly to give
    # the IP cap tests a deterministic key (ws:conn:127.0.0.1).
    from config.asgi import application
    communicator = WebsocketCommunicator(application, "/ws/vehicles/")
    communicator.scope["client"] = ("127.0.0.1", 12345)
    return communicator


async def _broadcast(payload: dict) -> None:
    layer = get_channel_layer()
    await layer.group_send(
        VEHICLES_ALL_GROUP,
        {"type": "vehicles.broadcast", "data": payload},
    )


# --- 1. connect accepts + group join (broadcast forwarded) ---------------


@pytest.mark.asyncio
async def test_connect_accepts_and_joins_group(fake_async_redis):
    communicator = _make_communicator()
    connected, _ = await communicator.connect()
    assert connected is True

    await _broadcast({"hello": "world"})
    msg = await communicator.receive_json_from()
    assert msg == {"hello": "world"}

    await communicator.disconnect()


# --- 2. initial snapshot sent when key present ----------------------------


@pytest.mark.asyncio
async def test_initial_snapshot_sent_when_present(fake_async_redis):
    snapshot = {
        "type": "vehicles_all_update",
        "timestamp": "2026-04-26T12:00:00Z",
        "vehicle_count": 1,
        "mapped_count": 1,
        "vehicles": [
            {"id": "C-1", "lat": 41.0, "lon": 29.0, "bearing": None,
             "speed": None, "route_id": "29B"},
        ],
    }
    await fake_async_redis.set(VEHICLES_ALL_KEY, json.dumps(snapshot))

    communicator = _make_communicator()
    connected, _ = await communicator.connect()
    assert connected is True

    msg = await communicator.receive_json_from()
    assert msg == snapshot

    await communicator.disconnect()


# --- 3. no snapshot when key absent (L4.B silent wait) -------------------


@pytest.mark.asyncio
async def test_no_snapshot_when_key_absent(fake_async_redis):
    communicator = _make_communicator()
    connected, _ = await communicator.connect()
    assert connected is True

    # Nothing seeded → consumer must NOT send anything on its own.
    assert await communicator.receive_nothing(timeout=0.5)

    # Connection still alive: ping → pong sanity probe.
    await communicator.send_json_to({"action": "ping"})
    pong = await communicator.receive_json_from()
    assert pong == {"type": "pong"}

    await communicator.disconnect()


# --- 4. corrupt snapshot logged + skipped ---------------------------------


@pytest.mark.asyncio
async def test_corrupt_snapshot_logged_and_skipped(fake_async_redis, caplog):
    await fake_async_redis.set(VEHICLES_ALL_KEY, b"{not valid json")

    communicator = _make_communicator()
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        connected, _ = await communicator.connect()
        assert connected is True
        assert await communicator.receive_nothing(timeout=0.5)

    corrupt_warns = [
        r.getMessage() for r in caplog.records
        if r.levelno == logging.WARNING and "corrupt vehicles:all" in r.getMessage()
    ]
    assert len(corrupt_warns) == 1

    await communicator.disconnect()


# --- 5. group broadcast forwarded (multiple ticks) ------------------------


@pytest.mark.asyncio
async def test_group_broadcast_forwarded(fake_async_redis):
    communicator = _make_communicator()
    connected, _ = await communicator.connect()
    assert connected is True

    await _broadcast({"tick": 1})
    msg1 = await communicator.receive_json_from()
    assert msg1 == {"tick": 1}

    await _broadcast({"tick": 2})
    msg2 = await communicator.receive_json_from()
    assert msg2 == {"tick": 2}

    await communicator.disconnect()


# --- 6. ping → pong -------------------------------------------------------


@pytest.mark.asyncio
async def test_ping_returns_pong(fake_async_redis):
    communicator = _make_communicator()
    connected, _ = await communicator.connect()
    assert connected is True

    await communicator.send_json_to({"action": "ping"})
    msg = await communicator.receive_json_from()
    assert msg == {"type": "pong"}

    await communicator.disconnect()


# --- 7. unknown action logged + dropped (L6.A) ---------------------------


@pytest.mark.asyncio
async def test_unknown_action_logged_and_dropped(fake_async_redis, caplog):
    communicator = _make_communicator()
    connected, _ = await communicator.connect()
    assert connected is True

    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        await communicator.send_json_to(
            {"action": "subscribe", "route_ids": ["29B"]},
        )
        # No reply — "subscribe" is not implemented in v0.8 (Faz 5 will
        # bring it back). Consumer drops silently with a warning.
        assert await communicator.receive_nothing(timeout=0.5)

    unknown_warns = [
        r.getMessage() for r in caplog.records
        if r.levelno == logging.WARNING and "unknown action" in r.getMessage()
    ]
    assert len(unknown_warns) == 1

    await communicator.disconnect()


# --- 8. IP cap rejects beyond limit ---------------------------------------


@pytest.mark.asyncio
async def test_ip_cap_rejects_sixth_connection(fake_async_redis, settings):
    settings.WS_MAX_CONN_PER_IP = 2

    c1 = _make_communicator()
    c2 = _make_communicator()
    c3 = _make_communicator()

    connected1, _ = await c1.connect()
    connected2, _ = await c2.connect()
    assert connected1 is True
    assert connected2 is True

    # Third connect must be rejected with close code 4008.
    connected3, code3 = await c3.connect()
    assert connected3 is False
    assert code3 == 4008

    # After releasing one slot, a fresh connect succeeds — proves the
    # rejection path rolled back the counter (DECR on cap-exceed branch).
    await c1.disconnect()
    c4 = _make_communicator()
    connected4, _ = await c4.connect()
    assert connected4 is True

    await c2.disconnect()
    await c4.disconnect()


# --- 9. disconnect decrements IP counter ---------------------------------


@pytest.mark.asyncio
async def test_disconnect_decrements_ip_counter(fake_async_redis, settings):
    settings.WS_MAX_CONN_PER_IP = 1

    communicator = _make_communicator()
    connected, _ = await communicator.connect()
    assert connected is True

    # Counter is 1 after a successful connect.
    raw = await fake_async_redis.get("ws:conn:127.0.0.1")
    assert raw is not None and int(raw) == 1

    await communicator.disconnect()

    # Counter dropped back to 0 — slot is reusable.
    raw_after = await fake_async_redis.get("ws:conn:127.0.0.1")
    assert raw_after is not None and int(raw_after) == 0
