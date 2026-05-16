"""Celery tasks for realtime adapter orchestration.

Phase 2 Step 5b-iii owns ``refresh_iett_mapping`` — the daily job that
pulls yesterday's completed İETT tasks, reshapes them via
``build_mapping``, and writes the payload to Redis under
``iett:mapping:current`` (spec §5.7 + Ek A.13).

Phase 3 Step 6c owns ``fetch_iett_positions`` — the per-tick job that
pulls live vehicle positions, enriches them with the cached mapping,
and publishes a single fleet-wide snapshot via Channels group_send
(group ``vehicles_all``) plus a SET ``vehicles:all`` for last-known
state. Per-route fanout was retired with the v0.8 UX pivot — every
vehicle (mapped or not) now lands in the same payload, frontend draws
ham points and reads ``route_id`` for popup labels.

Beat schedule (Step 5e) binds both to cron-like intervals.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone

import redis
import requests
from asgiref.sync import async_to_sync
from celery import shared_task
from channels.layers import get_channel_layer
from django.conf import settings
from django.utils import timezone

from apps.core.constants import (
    IETT_COOLDOWN_MINUTES,
    IETT_RATE_LIMIT_MAX_CALLS,
    IETT_RATE_LIMIT_SOFT_CALLS,
    IETT_RATE_LIMIT_WINDOW_MINUTES,
)
from apps.realtime.adapters.iett_soap import IettRateLimitViolation, IettSoapAdapter
from apps.realtime.calendar import ISTANBUL_TZ, get_day_type, pick_target_date
from apps.realtime.enrich import enrich_with_route_id
from apps.realtime.mapping import build_mapping
from apps.realtime.rate_limit import SlidingWindowLimiter
from apps.realtime.spatial import get_route_shape_cache, is_vehicle_near_route

logger = logging.getLogger(__name__)

MAPPING_CACHE_KEY = "iett:mapping:current"
MAPPING_CACHE_TTL_SECONDS = 28 * 3600  # 28 hours — spec §5.7

VEHICLES_ALL_KEY = "vehicles:all"            # fleet-wide snapshot (REST fallback in 6e)
VEHICLES_ALL_GROUP = "vehicles_all"          # Channels group consumers join in 6d
VEHICLES_CACHE_TTL_SECONDS = 120             # spec §5.7
UNMAPPED_COUNT_KEY = "stats:unmapped_count"
LAST_FETCH_TS_KEY = "stats:last_fetch_ts"
DAY_TYPE_MISMATCH_COUNT_KEY = "stats:day_type_mismatch_count"  # 5i-iv
STALE_VEHICLE_DROPPED_COUNT_KEY = "stats:stale_vehicle_dropped_count"  # 2026-05-02


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


@shared_task(name="apps.realtime.tasks.refresh_iett_mapping", bind=True)
def refresh_iett_mapping(self) -> dict:
    """Fetch the appropriate İETT archive, build mapping, write to Redis.

    Runs once daily at 04:00 TR time (beat schedule in Step 5e).

    Target-date selection (5i-iii): instead of "yesterday", uses
    :func:`apps.realtime.calendar.pick_target_date` which returns the
    last same-weekday archive (Mon→last Mon etc.), with holiday-aware
    fallbacks (today=holiday → last Sunday; 7-day-back=holiday → 14-day;
    14 also holiday → alarm + last Sunday).

    On failure we return an error dict — **no Celery retry**. Retrying
    into a live incident would just burn the shared rate-limit budget;
    tomorrow's run takes over. On failure the previous day's Redis
    payload is untouched, so consumers keep serving stale-but-coherent
    data until recovery.

    The returned dict also feeds the "Live Vehicles" admin page (Step 5f).
    """
    started = time.monotonic()
    today = timezone.localtime().date()
    target_date, day_type = pick_target_date(today)

    logger.info(
        "refresh_iett_mapping: starting (today=%s target=%s day_type=%s)",
        today.isoformat(), target_date.isoformat(), day_type,
    )

    redis_client = redis.from_url(settings.REDIS_URL, decode_responses=False)
    adapter = _make_adapter(redis_client)

    try:
        records = adapter.fetch_arsiv_gorev(target_date)
    except IettRateLimitViolation as exc:
        logger.error(
            "refresh_iett_mapping: rate-limit violation, cooldown armed: %s", exc,
        )
        return {
            "status": "error",
            "error_type": "rate_limit_violation",
            "error": str(exc),
            "today": today.isoformat(),
            "target_date": target_date.isoformat(),
            "day_type": day_type,
            "elapsed_seconds": round(time.monotonic() - started, 2),
        }
    except requests.HTTPError as exc:
        logger.error("refresh_iett_mapping: upstream HTTP error: %s", exc)
        return {
            "status": "error",
            "error_type": "http_error",
            "error": str(exc),
            "today": today.isoformat(),
            "target_date": target_date.isoformat(),
            "day_type": day_type,
            "elapsed_seconds": round(time.monotonic() - started, 2),
        }
    except Exception as exc:
        logger.exception("refresh_iett_mapping: unexpected adapter failure")
        return {
            "status": "error",
            "error_type": exc.__class__.__name__,
            "error": str(exc),
            "today": today.isoformat(),
            "target_date": target_date.isoformat(),
            "day_type": day_type,
            "elapsed_seconds": round(time.monotonic() - started, 2),
        }

    mapping = build_mapping(records, target_date, day_type)

    active = set(mapping["active_routes"])
    metrobus_missing = sorted(settings.METROBUS_SHORT_NAMES - active)
    metrobus_present_count = len(settings.METROBUS_SHORT_NAMES) - len(metrobus_missing)

    payload_bytes = json.dumps(mapping, separators=(",", ":")).encode("utf-8")
    redis_client.set(
        MAPPING_CACHE_KEY,
        payload_bytes,
        ex=MAPPING_CACHE_TTL_SECONDS,
    )
    # 5i-iv: reset mismatch counter on every successful refresh.
    # Race window with fetch incr is ~1-2 s; worst case we lose one
    # mismatch tick. Polish (race-free pattern) tracked in ROADMAP 5j.
    redis_client.set(DAY_TYPE_MISMATCH_COUNT_KEY, 0)

    elapsed = round(time.monotonic() - started, 2)
    result = {
        "status": "ok",
        "today": today.isoformat(),
        "target_date": target_date.isoformat(),
        "day_type": day_type,
        "records_received": len(records),
        "active_routes_count": len(active),
        "metrobus_coverage": f"{metrobus_present_count}/{len(settings.METROBUS_SHORT_NAMES)}",
        "metrobus_missing": metrobus_missing,
        "payload_bytes": len(payload_bytes),
        "elapsed_seconds": elapsed,
    }
    logger.info("refresh_iett_mapping: SUCCESS %s", result)
    return result


def _utcnow() -> datetime:
    """Indirection seam for tests — patch ``tasks_module._utcnow`` to
    pin the wall clock and exercise the stale-vehicle-timestamp filter
    deterministically."""
    return datetime.now(tz=dt_timezone.utc)


def _now_iso_z() -> str:
    """UTC now as ``YYYY-MM-DDTHH:MM:SSZ`` (spec §5.3 example format)."""
    return (
        _utcnow()
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


@shared_task(name="apps.realtime.tasks.fetch_iett_positions")
def fetch_iett_positions() -> dict:
    """Tick the live-positions pipeline (spec §5.7, ROADMAP 6c).

    One pass per tick (60 s, scheduled in Step 5e):
      1. ``adapter.fetch()`` → ``list[VehiclePosition]``
      2. Read ``iett:mapping:current``; ``json.loads`` if present.
         Cache miss → empty mapping (every vehicle ends up unmapped),
         WARNING log; broadcast still happens so the frontend keeps
         drawing ham points.
      3. ``enrich_with_route_id`` stamps ``route_id`` (None for
         unmapped vehicles — kept in payload per UX pivot).
      4. Single-pass mapped/unmapped count (no groupby needed in
         vehicles:all model).
      5. Overwrite ``stats:unmapped_count`` (always written, even when
         zero — observability heartbeat).
      6. Build the fleet-wide payload, ``SET vehicles:all`` (TTL 120 s)
         for REST fallback (6e), ``async_to_sync(channel_layer
         .group_send)`` to ``vehicles_all`` for live consumers (6d).
         The empty-fleet case still broadcasts a zero-payload — the
         frontend MUST get a heartbeat or it can't tell stale from idle.

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

    # 5i-iv: sample-based day_type mismatch detection. enrich.py stays a
    # pure best-effort lookup; the counter is bookkeeping for the admin
    # alarm. Overnight continuation is detected the same way as in enrich
    # (vehicle on snapshot+1 day before 04:00) and does NOT count as a
    # mismatch — it's an expected window.
    if vehicles and mapping:
        sample_local = vehicles[0].timestamp.astimezone(ISTANBUL_TZ)
        today_dt = get_day_type(sample_local.date())
        snapshot_dt = mapping.get("snapshot_day_type")
        snapshot_date_str = mapping.get("snapshot_date")

        is_overnight = False
        if snapshot_date_str:
            try:
                snap_date = date.fromisoformat(snapshot_date_str)
                is_overnight = (
                    sample_local.date() == snap_date + timedelta(days=1)
                    and sample_local.hour < 4
                )
            except ValueError:
                pass  # corrupt snapshot_date → treat as not overnight

        if (
            snapshot_dt is not None
            and today_dt != snapshot_dt
            and not is_overnight
        ):
            logger.warning(
                "fetch_iett_positions: day_type mismatch — degraded mode "
                "(today=%s mapping=%s snapshot_date=%s)",
                today_dt, snapshot_dt, snapshot_date_str,
            )
            redis_client.incr(DAY_TYPE_MISMATCH_COUNT_KEY)

    # 2026-05-02 stale-fleet-timestamp filter: enrich demotes route_id to
    # None when v.timestamp drifts beyond STALE_VEHICLE_TIMESTAMP_THRESHOLD_S
    # (180s) from reference_now in either direction. The same _utcnow seam
    # feeds _now_iso_z below for the snapshot top-level timestamp, so the
    # filter's reference and the snapshot's recorded enrich-time agree.
    reference_now = _utcnow()
    enriched, stale_dropped = enrich_with_route_id(
        vehicles, mapping, reference_now=reference_now,
    )

    # Spatial sanity check (6h-i): mapping kapı→hat zaman bazlıdır,
    # gerçek konum bilgisi içermez. Sefer bitiminde garaja dönen ya
    # da molada olan araçlar mapping'de "hat üzerindeymiş gibi"
    # etiketlenir. Burada her mapped vehicle'ı route shape pool'una
    # karşı kontrol eder, threshold ihlali varsa route_id null'larız.
    # VehiclePosition Pydantic frozen — in-place setattr ValidationError
    # fırlatır, model_copy(update=...) ile yeni instance üretiyoruz.
    # Cache miss = "shape kaynağı yok" → mapping'e güven, dokunma
    # (6h-i-fix-2): İETT GTFS feed'i shape içermediği için aksi halde
    # canlı akıştaki her aracı null'lardık. Detay spatial.py docstring.
    spatial_input = sum(1 for v in enriched if v.route_id is not None)
    skipped_no_shape = 0
    nullified_off_route = 0
    passed_check = 0
    if spatial_input:
        cache = get_route_shape_cache()
        new_enriched = []
        for v in enriched:
            if v.route_id is None:
                new_enriched.append(v)
                continue
            shape_arr = cache.get(v.route_id)
            if shape_arr is None:
                skipped_no_shape += 1
                new_enriched.append(v)
                continue
            if not is_vehicle_near_route(v.latitude, v.longitude, shape_arr):
                new_enriched.append(v.model_copy(update={"route_id": None}))
                nullified_off_route += 1
                continue
            new_enriched.append(v)
            passed_check += 1
        enriched = new_enriched
        logger.info(
            "spatial_check: input=%d skipped_no_shape=%d "
            "nullified_off_route=%d passed=%d",
            spatial_input,
            skipped_no_shape,
            nullified_off_route,
            passed_check,
        )

    mapped_count = sum(1 for v in enriched if v.route_id is not None)
    unmapped = len(enriched) - mapped_count

    redis_client.set(UNMAPPED_COUNT_KEY, unmapped)
    # Heartbeat semantics: every tick overwrites with the per-tick drop
    # count (not cumulative). Mirrors UNMAPPED_COUNT_KEY pattern.
    redis_client.set(STALE_VEHICLE_DROPPED_COUNT_KEY, stale_dropped)

    # Heartbeat: only success paths reach here (any adapter exception
    # returned early). Cache miss still counts as success — the upstream
    # was healthy, only the mapping was missing.
    now_iso = _now_iso_z()
    redis_client.set(LAST_FETCH_TS_KEY, now_iso)

    payload = {
        "type": "vehicles_all_update",
        "timestamp": now_iso,
        "vehicle_count": len(enriched),
        "vehicles": [
            {
                "id": v.vehicle_id,
                "lat": v.latitude,
                "lon": v.longitude,
                "bearing": v.bearing,
                "speed": v.speed,
                "route_id": v.route_id,
                "is_metrobus": v.is_metrobus,
            }
            for v in enriched
        ],
    }
    payload_json = json.dumps(payload, separators=(",", ":"))
    redis_client.set(VEHICLES_ALL_KEY, payload_json, ex=VEHICLES_CACHE_TTL_SECONDS)

    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        VEHICLES_ALL_GROUP,
        {"type": "vehicles.broadcast", "data": payload},
    )

    elapsed = round(time.monotonic() - started, 2)
    result = {
        "status": "ok",
        "fetched": len(vehicles),
        "unmapped": unmapped,
        "elapsed_seconds": elapsed,
    }
    logger.info("fetch_iett_positions: SUCCESS %s", result)
    return result
