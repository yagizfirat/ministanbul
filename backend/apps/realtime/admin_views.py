"""Read-only Live Vehicles dashboard view (Phase 2 Step 5f, MVP).

Aggregates five pipeline-health metrics from Redis for the operator's
admin page:

  1. Total active vehicles (from ``vehicles:all`` payload)
  2. Top 20 routes by vehicle count — unmapped vehicles appear as a
     ``(unmapped)`` bucket so mapping issues are visible, not hidden
  3. Unmapped count + percent (``stats:unmapped_count`` / total seen)
  4. Mapping cache presence + remaining TTL
  5. Last successful fetch timestamp + per-endpoint rate-limit snapshot
     (``IettSoapAdapter.health()`` via :func:`apps.realtime.tasks._make_adapter`)

Faz 3 6c: per-route ``vehicles:route:*`` keys gone — single
``vehicles:all`` snapshot is the source of truth. Counter aggregation
over ``vehicles[*].route_id`` reproduces the same per-route view, with
None bucket exposed as "(unmapped)" in the template.

Server-side render, manual F5 refresh — no auto-refresh, no polling.
The auth wrapper is applied where the URL is wired up (admin.py uses
``admin.site.admin_view``); this module assumes the request is already
staff-authenticated.
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import date, datetime

import redis
from django.conf import settings
from django.shortcuts import render

from apps.realtime.calendar import ISTANBUL_TZ
from apps.realtime.tasks import (
    DAY_TYPE_MISMATCH_COUNT_KEY,
    LAST_FETCH_TS_KEY,
    MAPPING_CACHE_KEY,
    UNMAPPED_COUNT_KEY,
    VEHICLES_ALL_KEY,
    _make_adapter,
)

logger = logging.getLogger(__name__)


def live_vehicles_view(request):
    """Render the dashboard. All Redis reads are best-effort: a corrupt
    payload or unavailable limiter degrades to a placeholder, never a
    500."""
    redis_client = redis.from_url(settings.REDIS_URL, decode_responses=False)

    # 1 + 2. vehicles:all snapshot → Counter over route_id (None included
    # as "(unmapped)" bucket so operators see mapping issues directly).
    raw_snapshot = redis_client.get(VEHICLES_ALL_KEY)
    counter: Counter = Counter()
    if raw_snapshot:
        try:
            snapshot = json.loads(raw_snapshot)
            counter = Counter(
                v.get("route_id") for v in snapshot.get("vehicles", [])
            )
        except json.JSONDecodeError:
            logger.warning("admin: corrupt vehicles:all payload")

    total_vehicles = sum(counter.values())
    active_routes = len(counter) - (1 if None in counter else 0)
    top_routes = sorted(counter.items(), key=lambda kv: kv[1], reverse=True)[:20]

    # 3. Unmapped count + percentage.
    raw_unmapped = redis_client.get(UNMAPPED_COUNT_KEY)
    unmapped_count = int(raw_unmapped) if raw_unmapped else 0
    total_seen = total_vehicles + unmapped_count
    unmapped_percent = (
        round(100 * unmapped_count / total_seen, 1) if total_seen else 0.0
    )

    # 4. Mapping cache presence + remaining TTL (hours) + snapshot metadata.
    mapping_ttl = redis_client.ttl(MAPPING_CACHE_KEY)  # -2 absent, -1 no TTL, >=0 ttl
    mapping_present = mapping_ttl >= -1
    mapping_ttl_hours = round(mapping_ttl / 3600, 1) if mapping_ttl > 0 else None

    mapping_snapshot_date = None
    mapping_snapshot_day_type = None
    mapping_age_days = None
    if mapping_present:
        raw_mapping = redis_client.get(MAPPING_CACHE_KEY)
        if raw_mapping:
            try:
                mapping_payload = json.loads(raw_mapping)
                mapping_snapshot_date = mapping_payload.get("snapshot_date")
                mapping_snapshot_day_type = mapping_payload.get("snapshot_day_type")
                if mapping_snapshot_date:
                    snap = date.fromisoformat(mapping_snapshot_date)
                    today = datetime.now(tz=ISTANBUL_TZ).date()
                    mapping_age_days = (today - snap).days
            except (json.JSONDecodeError, ValueError):
                logger.warning("admin: mapping payload parse failed")

    # 5a. Last successful fetch heartbeat.
    raw_last_fetch = redis_client.get(LAST_FETCH_TS_KEY)
    last_fetch_ts = raw_last_fetch.decode("utf-8") if raw_last_fetch else None

    # 5c. Day-type mismatch counter (5i-iv).
    raw_mismatch = redis_client.get(DAY_TYPE_MISMATCH_COUNT_KEY)
    mismatch_count = int(raw_mismatch) if raw_mismatch else 0

    # 5b. Rate-limit snapshots (one for fleet, one for arsiv).
    try:
        adapter = _make_adapter(redis_client)
        health = adapter.health()
        fleet_limiter = health["fleet_limiter"]
        arsiv_limiter = health["arsiv_limiter"]
    except Exception:
        logger.exception("admin: adapter.health() failed")
        fleet_limiter = None
        arsiv_limiter = None

    context = {
        "title": "Live Vehicles",
        "total_vehicles": total_vehicles,
        "active_routes": active_routes,
        "top_routes": top_routes,
        "unmapped_count": unmapped_count,
        "unmapped_percent": unmapped_percent,
        "mapping_present": mapping_present,
        "mapping_ttl_hours": mapping_ttl_hours,
        "mapping_snapshot_date": mapping_snapshot_date,
        "mapping_snapshot_day_type": mapping_snapshot_day_type,
        "mapping_age_days": mapping_age_days,
        "last_fetch_ts": last_fetch_ts,
        "mismatch_count": mismatch_count,
        "fleet_limiter": fleet_limiter,
        "arsiv_limiter": arsiv_limiter,
    }
    return render(request, "admin/realtime/live_vehicles.html", context)
