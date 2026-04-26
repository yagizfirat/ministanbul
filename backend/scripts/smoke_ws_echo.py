"""WebSocket echo smoke — gerçek Daphne process üstünden network round-trip.

WebsocketCommunicator (test_consumer_echo.py) consumer'ı in-process
çalıştırır, network katmanını atlar. Bu script Daphne'nin TCP socket'ini,
HTTP→WS upgrade handshake'ini, ve channels-redis layer'ını fiilen
test eder.

Kullanım:
    1. Ayrı terminalde Daphne başlat:
       bash backend/scripts/run_daphne.sh
    2. python backend/scripts/smoke_ws_echo.py

Exit codes:
    0 — round-trip başarılı
    1 — bağlantı/protokol hatası
    2 — payload mismatch
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import datetime, timezone

from websockets.asyncio.client import connect

WS_URL = "ws://localhost:8011/ws/echo/"
TIMEOUT_SECONDS = 5.0


async def run_smoke() -> int:
    sentinel = {"smoke": "test", "ts": datetime.now(timezone.utc).isoformat()}
    serialized = json.dumps(sentinel)

    try:
        async with asyncio.timeout(TIMEOUT_SECONDS):
            async with connect(WS_URL) as ws:
                t0 = time.perf_counter()
                await ws.send(serialized)
                reply_raw = await ws.recv()
                rtt_ms = (time.perf_counter() - t0) * 1000.0
    except (OSError, asyncio.TimeoutError) as e:
        print(f"FAIL: connection/timeout — {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"FAIL: unexpected — {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    try:
        reply = json.loads(reply_raw)
    except json.JSONDecodeError as e:
        print(f"FAIL: reply not JSON — {e}\nraw: {reply_raw!r}", file=sys.stderr)
        return 2

    expected = {"echo": sentinel}
    if reply != expected:
        print(f"FAIL: payload mismatch", file=sys.stderr)
        print(f"  expected: {expected}", file=sys.stderr)
        print(f"  received: {reply}", file=sys.stderr)
        return 2

    print(f"OK: echo round-trip {rtt_ms:.1f}ms at {WS_URL}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run_smoke()))
