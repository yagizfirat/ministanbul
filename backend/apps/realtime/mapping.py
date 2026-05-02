"""Pure helper that reshapes parsed archive records into the cache payload.

Consumed by the mapping-refresh Celery task (Adım 5b-iii): the task
fetches a day of archive records via ``IettSoapAdapter.fetch_arsiv_gorev``
and passes the parsed list here; the return value is serialised to JSON
and written to Redis under ``iett:mapping:current`` per spec §5.7.

Phase 2 Step 5i-i refactor: intervals are stored as wall-clock seconds
(Istanbul TZ) per snapshot day, plus a ``snapshot_day_type`` metadata
field. Overnight tasks (start same day, end next day) extend ``end_sec``
beyond 86400. Tasks whose start does not fall on ``snapshot_date`` are
skipped — only same-day or overnight-from-snapshot intervals are kept.

Keeping the reshaping in a pure function means tests can check the shape
without fakeredis, and the refresh task stays a thin wrapper around
``fetch + build + redis.set``.
"""
from __future__ import annotations

import datetime
import logging
from collections import defaultdict

from apps.core.constants import METROBUS_ROUTES
from apps.realtime.calendar import ISTANBUL_TZ
from apps.realtime.schemas import IettArsivGorev

logger = logging.getLogger(__name__)


def _build_route_id_by_short_name(active_routes: set[str]) -> dict[str, str]:
    """Return ``{short_name: canonical Route.route_id}`` for the active SHATKODU set.

    Yol B (frontend route_id contract): vehicle.route_id must carry the
    GTFS Route.route_id (e.g. ``"iett:1562"``), not the SHATKODU short_name
    (``"29B"``). Frontend RouteStore is keyed by route_id; without this
    translation, panel filter / focus / popup silent-fail for buses.

    Selection policy (β filter): IETT agency only (name lookup, since
    agency.id is environment-dependent) AND ``route_type=3`` (bus, excludes
    metrobus-shaped trams etc. that share short_names). Among the resulting
    1:N rows, ``ORDER BY route_id ASC`` gives the deterministic canonical
    pick — recon report 2026-05-01 confirmed this matches the existing
    panel ``iett:1562`` choice for 29B.

    Defensive fallback: if the IETT Agency row is missing (clean test DB,
    pre-import state) OR DB access fails (pytest-django blocker without
    ``django_db`` marker, transient connection error), we return an empty
    dict. The mapping payload still serialises; ``enrich_with_route_id``
    consumers handle the lookup miss as ``route_id=None`` per spec.
    """
    if not active_routes:
        return {}

    try:
        from apps.gtfs.models import Agency, Route

        iett_agency_id = Agency.objects.values_list("id", flat=True).get(name="IETT")
        rows = (
            Route.objects
            .filter(
                short_name__in=active_routes,
                agency_id=iett_agency_id,
                route_type=Route.ROUTE_TYPE_BUS,
            )
            .values_list("short_name", "route_id")
            .order_by("route_id")
        )
        canonical: dict[str, str] = {}
        for short_name, route_id in rows:
            # First row per short_name wins — query is ORDER BY route_id ASC.
            canonical.setdefault(short_name, route_id)
        return canonical
    except Exception as exc:  # noqa: BLE001 — graceful degrade
        logger.warning(
            "build_mapping: route_id_by_short_name disabled (%s: %s); "
            "vehicles will resolve route_id=None until DB is reachable",
            type(exc).__name__, exc,
        )
        return {}


def _seconds_of_day(dt_local: datetime.datetime) -> int:
    """Wall-clock seconds since midnight (0..86399) for a local-aware datetime."""
    return dt_local.hour * 3600 + dt_local.minute * 60 + dt_local.second


def build_mapping(
    records: list[IettArsivGorev],
    snapshot_date: datetime.date,
    snapshot_day_type: str,
) -> dict:
    """Return the KapiNo → tasks mapping payload (spec §5.7, post-5i-i format).

    Expected input: a list of ``IettArsivGorev`` already filtered upstream
    (parser drops non-T status and null timestamps). This helper does not
    re-validate; it just reshapes.

    ``snapshot_day_type`` is one of ``"weekday"`` / ``"saturday"`` /
    ``"sunday"`` and identifies which schedule day the snapshot represents.
    Enrich-side checks this against the live vehicle's day type to detect
    a stale-mapping degraded mode (5i-ii / 5i-iv).

    Per-KapiNo task lists are sorted by ``start_sec`` ascending so the
    fetch task's ``bisect_right`` lookup is O(log n).

    Output shape::

        {
            "snapshot_date": "YYYY-MM-DD",
            "snapshot_day_type": "weekday" | "saturday" | "sunday",
            "by_kapi": {
                "C-231": [
                    {"start_sec": int, "end_sec": int,   # seconds since midnight, IST
                     "hat": str, "guzergah": str},       # end_sec >= 86400 means
                    ...                                   # overnight (extends into
                ],                                        # the day after snapshot)
                ...
            },
            "active_routes": [...],        # sorted unique SHATKODU
            "routes_by_mode": {
                "metrobus": [...],         # METROBUS_ROUTES ∩ active
                "bus":      [...],         # active - METROBUS_ROUTES
            },
            "route_id_by_short_name": {    # SHATKODU → GTFS Route.route_id
                "29B": "iett:1562", ...    # canonical PK per active short_name
            },
        }

    Skip rules:
      - Empty ``kapi_no`` → ``empty_kapi``
      - Task whose start does not fall on ``snapshot_date`` (Istanbul) →
        ``outside_snapshot``
      - Task that ends more than one day after ``snapshot_date`` →
        ``outside_snapshot``
      - ``end_sec < start_sec`` after extension logic → ``inverted``

    Other modes (metro/tram/funicular/marmaray/ferry) are absent by
    design — they don't come from the İETT feed.
    """
    by_kapi: dict[str, list[dict]] = defaultdict(list)
    active_routes: set[str] = set()

    empty_kapi_skipped = 0
    inverted_skipped = 0
    outside_snapshot_skipped = 0

    next_date = snapshot_date + datetime.timedelta(days=1)

    for rec in records:
        kapi = rec.kapi_no
        if not kapi:
            empty_kapi_skipped += 1
            continue

        local_start = rec.start_time.astimezone(ISTANBUL_TZ)
        local_end = rec.end_time.astimezone(ISTANBUL_TZ)

        if local_start.date() != snapshot_date:
            outside_snapshot_skipped += 1
            continue

        if local_end.date() == snapshot_date:
            # Same-day task.
            start_sec = _seconds_of_day(local_start)
            end_sec = _seconds_of_day(local_end)
        elif local_end.date() == next_date:
            # Overnight task — extend end_sec past 86400.
            start_sec = _seconds_of_day(local_start)
            end_sec = 86400 + _seconds_of_day(local_end)
        else:
            # Ends two-or-more days later — out of scope for a daily snapshot.
            outside_snapshot_skipped += 1
            continue

        if end_sec < start_sec:
            inverted_skipped += 1
            logger.warning(
                "build_mapping: inverted interval dropped "
                "(kapi=%s hat=%s start_sec=%d end_sec=%d)",
                kapi, rec.hat_kodu, start_sec, end_sec,
            )
            continue

        by_kapi[kapi].append({
            "start_sec": start_sec,
            "end_sec": end_sec,
            "hat": rec.hat_kodu,
            "guzergah": rec.guzergah_kodu,
        })
        active_routes.add(rec.hat_kodu)

    for kapi_tasks in by_kapi.values():
        kapi_tasks.sort(key=lambda t: t["start_sec"])

    metrobus_active = sorted(active_routes & METROBUS_ROUTES)
    bus_active = sorted(active_routes - METROBUS_ROUTES)

    skip_total = empty_kapi_skipped + inverted_skipped + outside_snapshot_skipped
    if skip_total:
        logger.info(
            "build_mapping: total=%d kept=%d skipped=%d "
            "(empty_kapi=%d inverted=%d outside_snapshot=%d)",
            len(records),
            len(records) - skip_total,
            skip_total,
            empty_kapi_skipped, inverted_skipped, outside_snapshot_skipped,
        )

    return {
        "snapshot_date": snapshot_date.isoformat(),
        "snapshot_day_type": snapshot_day_type,
        "by_kapi": dict(by_kapi),
        "active_routes": sorted(active_routes),
        "routes_by_mode": {
            "metrobus": metrobus_active,
            "bus": bus_active,
        },
        "route_id_by_short_name": _build_route_id_by_short_name(active_routes),
    }
