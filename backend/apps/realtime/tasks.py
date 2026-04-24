"""Celery tasks for realtime adapter orchestration.

Phase 2 Step 5b-iii owns ``refresh_iett_mapping`` — the daily job that
pulls yesterday's completed İETT tasks, reshapes them via
``build_mapping``, and writes the payload to Redis under
``iett:mapping:current`` (spec §5.7 + Ek A.13).

The per-minute ``fetch_iett_positions`` task (Step 5d) will land in a
later commit; beat schedule (Step 5e) binds both to cron-like intervals.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import timedelta

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
from apps.realtime.mapping import build_mapping
from apps.realtime.rate_limit import SlidingWindowLimiter

logger = logging.getLogger(__name__)

MAPPING_CACHE_KEY = "iett:mapping:current"
MAPPING_CACHE_TTL_SECONDS = 28 * 3600  # 28 hours — spec §5.7


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
