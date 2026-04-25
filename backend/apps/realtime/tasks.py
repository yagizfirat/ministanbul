"""Celery tasks for realtime adapter orchestration.

Phase 2 Step 5b-iii owns ``refresh_iett_mapping`` — the daily job that
pulls yesterday's completed İETT tasks, reshapes them via
``build_mapping``, and writes the payload to Redis under
``iett:mapping:current`` (spec §5.7 + Ek A.13).

Phase 2 Step 5d owns ``fetch_iett_positions`` — the per-tick job that
pulls live vehicle positions, enriches them with the cached mapping,
and publishes route-grouped snapshots to Redis pub/sub channels
(``vehicles:route:{short_name}``) plus a SET for last-known-state.

Beat schedule (Step 5e) binds both to cron-like intervals.
"""
from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

import redis
import requests
from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.core.constants import (
    IETT_COOLDOWN_MINUTES,
    IETT_RATE_LIMIT_MAX_CALLS,
    IETT_RATE_LIMIT_SOFT_CALLS,
    IETT_RATE_LIMIT_WINDOW_MINUTES,
    METROBUS_ROUTES,
)
from apps.realtime.adapters.iett_soap import IettRateLimitViolation, IettSoapAdapter
from apps.realtime.enrich import enrich_with_route_id
from apps.realtime.mapping import build_mapping
from apps.realtime.rate_limit import SlidingWindowLimiter

logger = logging.getLogger(__name__)

MAPPING_CACHE_KEY = "iett:mapping:current"
MAPPING_CACHE_TTL_SECONDS = 28 * 3600  # 28 hours — spec §5.7

VEHICLES_CACHE_KEY_PREFIX = "vehicles:route:"
VEHICLES_CACHE_TTL_SECONDS = 120  # spec §5.7
UNMAPPED_COUNT_KEY = "stats:unmapped_count"
LAST_FETCH_TS_KEY = "stats:last_fetch_ts"


def _make_adapter(redis_client) -> IettSoapAdapter:
    """Wire a per-run adapter with its own fleet/archive limiters.

    Limiters share the supplied ``redis_client`` so state is visible
    to every worker in the pool — the sliding window is process-shared.
    """
    window_s = IETT_RATE_LIMIT_WINDOW_MINUTES * 60
    cooldown_s = IETT_COOLDOWN_MINUTES * 60
    fleet_limiter = SlidingWindowLimiter(
        redis_client=redis_client,
        name="iett:ratelimit:fleet",
        window_seconds=window_s,
        soft_limit=IETT_RATE_LIMIT_SOFT_CALLS,
        hard_limit=IETT_RATE_LIMIT_MAX_CALLS,
        cooldown_seconds=cooldown_s,
    )
    arsiv_limiter = SlidingWindowLimiter(
        redis_client=redis_client,
        name="iett:ratelimit:arsiv",
        window_seconds=window_s,
        soft_limit=IETT_RATE_LIMIT_SOFT_CALLS,
        hard_limit=IETT_RATE_LIMIT_MAX_CALLS,
        cooldown_seconds=cooldown_s,
    )
    return IettSoapAdapter(
        redis_client=redis_client,
        fleet_limiter=fleet_limiter,
        arsiv_limiter=arsiv_limiter,
    )


@shared_task(name="apps.realtime.refresh_iett_mapping", bind=True)
def refresh_iett_mapping(self) -> dict:
    """Fetch yesterday's İETT archive, build mapping, write to Redis.

    Runs once daily at 04:00 TR time (beat schedule in Step 5e).

    On failure we return an error dict — **no Celery retry**. Retrying
    into a live incident would just burn the shared rate-limit budget;
    tomorrow's run takes over. On failure the previous day's Redis
    payload is untouched, so consumers keep serving stale-but-coherent
    data until recovery.

    The returned dict also feeds the "Live Vehicles" admin page (Step 5f).
    """
    started = time.monotonic()
    yesterday = (timezone.localtime() - timedelta(days=1)).date()

    logger.info(
        "refresh_iett_mapping: starting for date=%s", yesterday.isoformat()
    )

    redis_client = redis.from_url(settings.REDIS_URL, decode_responses=False)
    adapter = _make_adapter(redis_client)

    try:
        records = adapter.fetch_arsiv_gorev(yesterday)
    except IettRateLimitViolation as exc:
        logger.error(
            "refresh_iett_mapping: rate-limit violation, cooldown armed: %s", exc,
        )
        return {
            "status": "error",
            "error_type": "rate_limit_violation",
            "error": str(exc),
            "date": yesterday.isoformat(),
            "elapsed_seconds": round(time.monotonic() - started, 2),
        }
    except requests.HTTPError as exc:
        logger.error("refresh_iett_mapping: upstream HTTP error: %s", exc)
        return {
            "status": "error",
            "error_type": "http_error",
            "error": str(exc),
            "date": yesterday.isoformat(),
            "elapsed_seconds": round(time.monotonic() - started, 2),
        }
    except Exception as exc:
        logger.exception("refresh_iett_mapping: unexpected adapter failure")
        return {
            "status": "error",
            "error_type": exc.__class__.__name__,
            "error": str(exc),
            "date": yesterday.isoformat(),
            "elapsed_seconds": round(time.monotonic() - started, 2),
        }

    mapping = build_mapping(records, yesterday)

    active = set(mapping["active_routes"])
    metrobus_missing = sorted(METROBUS_ROUTES - active)
    metrobus_present_count = len(METROBUS_ROUTES) - len(metrobus_missing)

    payload_bytes = json.dumps(mapping, separators=(",", ":")).encode("utf-8")
    redis_client.set(
        MAPPING_CACHE_KEY,
        payload_bytes,
        ex=MAPPING_CACHE_TTL_SECONDS,
    )

    elapsed = round(time.monotonic() - started, 2)
    result = {
        "status": "ok",
        "date": yesterday.isoformat(),
        "records_received": len(records),
        "active_routes_count": len(active),
        "metrobus_coverage": f"{metrobus_present_count}/{len(METROBUS_ROUTES)}",
        "metrobus_missing": metrobus_missing,
        "payload_bytes": len(payload_bytes),
        "elapsed_seconds": elapsed,
    }
    logger.info("refresh_iett_mapping: SUCCESS %s", result)
    return result


def _now_iso_z() -> str:
    """UTC now as ``YYYY-MM-DDTHH:MM:SSZ`` (spec §5.3 example format)."""
    return (
        datetime.now(tz=dt_timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


@shared_task(name="apps.realtime.tasks.fetch_iett_positions")
def fetch_iett_positions() -> dict:
    """Tick the live-positions pipeline (spec §5.7, ROADMAP 5d).

    One pass per tick (60 s, scheduled in Step 5e):
      1. ``adapter.fetch()`` → ``list[VehiclePosition]``
      2. Read ``iett:mapping:current``; ``json.loads`` if present.
         Cache miss → empty mapping (every vehicle ends up unmapped),
         WARNING log; the loop still runs so the unmapped counter
         tracks the gap.
      3. ``enrich_with_route_id`` stamps ``route_id``.
      4. Group by ``route_id`` (None bucket = unmapped, dropped).
      5. Overwrite ``stats:unmapped_count`` (always written, even when
         zero — observability-wise we want a heartbeat).
      6. Per-route Redis pipeline (``transaction=False`` — single
         producer, no atomicity needed; pipelining is just for round
         trips): ``SET vehicles:route:{short_name} payload EX 120`` +
         ``PUBLISH vehicles:route:{short_name} payload``.

    Adapter exceptions are caught and returned as an error dict — no
    Celery retry. The next tick is 60 s away anyway, and retrying into
    a live incident burns the shared rate-limit budget.
    """
    started = time.monotonic()
    redis_client = redis.from_url(settings.REDIS_URL, decode_responses=False)
    adapter = _make_adapter(redis_client)

    try:
        vehicles = adapter.fetch()
    except IettRateLimitViolation as exc:
        logger.error(
            "fetch_iett_positions: rate-limit violation, cooldown armed: %s", exc,
        )
        return {
            "status": "error",
            "error_type": "rate_limit_violation",
            "error": str(exc),
            "elapsed_seconds": round(time.monotonic() - started, 2),
        }
    except requests.HTTPError as exc:
        logger.error("fetch_iett_positions: upstream HTTP error: %s", exc)
        return {
            "status": "error",
            "error_type": "http_error",
            "error": str(exc),
            "elapsed_seconds": round(time.monotonic() - started, 2),
        }
    except Exception as exc:
        logger.exception("fetch_iett_positions: unexpected adapter failure")
        return {
            "status": "error",
            "error_type": exc.__class__.__name__,
            "error": str(exc),
            "elapsed_seconds": round(time.monotonic() - started, 2),
        }

    raw_mapping = redis_client.get(MAPPING_CACHE_KEY)
    if raw_mapping is None:
        logger.warning(
            "fetch_iett_positions: mapping cache miss (key=%s) — "
            "all %d vehicles will be unmapped",
            MAPPING_CACHE_KEY, len(vehicles),
        )
        mapping = {}
    else:
        mapping = json.loads(raw_mapping)

    enriched = enrich_with_route_id(vehicles, mapping)

    grouped: dict[str, list] = defaultdict(list)
    unmapped = 0
    for v in enriched:
        if v.route_id is None:
            unmapped += 1
        else:
            grouped[v.route_id].append(v)

    redis_client.set(UNMAPPED_COUNT_KEY, unmapped)

    # Heartbeat: only success paths reach here (any adapter exception
    # returned early). Cache miss still counts as success — the upstream
    # was healthy, only the mapping was missing.
    now_iso = _now_iso_z()
    redis_client.set(LAST_FETCH_TS_KEY, now_iso)

    if grouped:
        pipe = redis_client.pipeline(transaction=False)
        for short_name, vehicles_list in grouped.items():
            payload = json.dumps(
                {
                    "type": "route_vehicles_update",
                    "route_id": short_name,
                    "timestamp": now_iso,
                    "vehicles": [
                        {
                            "id": v.vehicle_id,
                            "lat": v.latitude,
                            "lon": v.longitude,
                            "bearing": v.bearing,
                            "speed": v.speed,
                        }
                        for v in vehicles_list
                    ],
                },
                separators=(",", ":"),
            )
            key = f"{VEHICLES_CACHE_KEY_PREFIX}{short_name}"
            pipe.set(key, payload, ex=VEHICLES_CACHE_TTL_SECONDS)
            pipe.publish(key, payload)
        pipe.execute()

    elapsed = round(time.monotonic() - started, 2)
    result = {
        "status": "ok",
        "fetched": len(vehicles),
        "unmapped": unmapped,
        "routes": len(grouped),
        "elapsed_seconds": elapsed,
    }
    logger.info("fetch_iett_positions: SUCCESS %s", result)
    return result
