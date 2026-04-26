"""WebSocket consumers. Echo is a smoke target — kept after VehicleAll
(6d) lands so isolated WS connectivity can still be verified."""
from __future__ import annotations

import json
import logging
from typing import Any

import redis.asyncio as aioredis
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings

from .tasks import VEHICLES_ALL_GROUP, VEHICLES_ALL_KEY

logger = logging.getLogger(__name__)

IP_CONN_TTL_SECONDS = 3600  # zombie counter eviction guard


class EchoConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        await self.accept()

    async def receive_json(self, content):
        await self.send_json({"echo": content})

    async def disconnect(self, code):
        pass


class VehicleAllConsumer(AsyncJsonWebsocketConsumer):
    """Live vehicle broadcast consumer (spec §6.4 v0.8 prelude).

    Connect → join ``vehicles_all`` group → forward fetch task
    broadcasts. No subscribe protocol — every connected client gets
    every tick. UX pivot model: frontend draws all vehicles, route
    filter is visual.
    """

    async def connect(self):
        ip = self._client_ip()
        self._ip_key = f"ws:conn:{ip}"

        # Atomic INCR + post-check. Race-safe: if 6th and 7th connect
        # concurrently both see count > cap, both rollback, both close.
        # Final state stays at the cap. settings.WS_MAX_CONN_PER_IP is
        # read per-connect (lazy) so override_settings + dev hot-reload
        # both work.
        client = aioredis.from_url(settings.CHANNELS_REDIS_URL)
        try:
            count = await client.incr(self._ip_key)
            await client.expire(self._ip_key, IP_CONN_TTL_SECONDS)
            if count > settings.WS_MAX_CONN_PER_IP:
                await client.decr(self._ip_key)
                await self.close(code=4008)
                return
        finally:
            await client.aclose()

        # Order: group_add → accept → snapshot. group_add before accept
        # guarantees no broadcast lost in the window between accept and
        # join. Frontend dedups on timestamp (Faz 4 design).
        await self.channel_layer.group_add(VEHICLES_ALL_GROUP, self.channel_name)
        await self.accept()
        await self._send_initial_snapshot()

    async def disconnect(self, code):
        if hasattr(self, "_ip_key"):
            client = aioredis.from_url(settings.CHANNELS_REDIS_URL)
            try:
                await client.decr(self._ip_key)
            finally:
                await client.aclose()
        await self.channel_layer.group_discard(
            VEHICLES_ALL_GROUP, self.channel_name,
        )

    async def receive_json(self, content: dict[str, Any]):
        action = content.get("action")
        if action == "ping":
            await self.send_json({"type": "pong"})
            return
        # Subscribe protocol returns in Faz 5 (rail/ferry per-route
        # channels). Until then unknown actions drop silently with a
        # warning so a stray frontend bug doesn't 400.
        logger.warning(
            "VehicleAllConsumer: unknown action=%r, ignored", action,
        )

    async def vehicles_broadcast(self, event: dict):
        """Group event handler — fetch task group_send'inden gelir.
        Channels event ``type: "vehicles.broadcast"`` → method name
        ``vehicles_broadcast`` (dot → underscore convention)."""
        await self.send_json(event["data"])

    # --- helpers ---

    def _client_ip(self) -> str:
        client = self.scope.get("client")
        return client[0] if client else "unknown"

    async def _send_initial_snapshot(self):
        client = aioredis.from_url(settings.REDIS_URL)
        try:
            raw = await client.get(VEHICLES_ALL_KEY)
        finally:
            await client.aclose()
        if raw is None:
            # Silent wait: first tick will broadcast, frontend gets the
            # first message there. No "empty snapshot" placeholder —
            # avoids confusing the client about whether it's connected.
            return
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning(
                "VehicleAllConsumer: corrupt vehicles:all key, "
                "skipping initial snapshot",
            )
            return
        await self.send_json(payload)
