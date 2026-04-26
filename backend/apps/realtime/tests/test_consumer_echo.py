"""EchoConsumer smoke (ROADMAP 6b-iv).

WebsocketCommunicator runs the consumer in-process — no real WebSocket
handshake or Daphne instance needed. Multi-message test guards the
receive_json loop, mirroring the 60s tick discipline VehicleAllConsumer
will need (6d)."""
import pytest
from channels.testing import WebsocketCommunicator

from config.asgi import application


@pytest.mark.asyncio
async def test_echo_connect_accepts():
    communicator = WebsocketCommunicator(application, "/ws/echo/")
    connected, _ = await communicator.connect()
    assert connected is True
    await communicator.disconnect()


@pytest.mark.asyncio
async def test_echo_round_trips_payload():
    communicator = WebsocketCommunicator(application, "/ws/echo/")
    connected, _ = await communicator.connect()
    assert connected is True
    await communicator.send_json_to({"hello": "world"})
    response = await communicator.receive_json_from()
    assert response == {"echo": {"hello": "world"}}
    await communicator.disconnect()


@pytest.mark.asyncio
async def test_echo_disconnect_clean():
    communicator = WebsocketCommunicator(application, "/ws/echo/")
    connected, _ = await communicator.connect()
    assert connected is True
    await communicator.disconnect()
    # No assertion needed — disconnect() raises if the consumer's
    # disconnect handler errors out.


@pytest.mark.asyncio
async def test_echo_handles_multiple_messages_on_same_connection():
    # receive_json döngüsü gerçekten döngü olmalı — 6d'de
    # VehicleAllConsumer 60sn'de bir mesaj alacak, single-shot olmaz.
    communicator = WebsocketCommunicator(application, "/ws/echo/")
    connected, _ = await communicator.connect()
    assert connected is True

    await communicator.send_json_to({"a": 1})
    first = await communicator.receive_json_from()
    assert first == {"echo": {"a": 1}}

    await communicator.send_json_to({"b": 2})
    second = await communicator.receive_json_from()
    assert second == {"echo": {"b": 2}}

    await communicator.disconnect()
