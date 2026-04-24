"""Pure helper that reshapes parsed archive records into the cache payload.

Consumed by the mapping-refresh Celery task (Adım 5b-iii): the task
fetches a day of archive records via ``IettSoapAdapter.fetch_arsiv_gorev``
and passes the parsed list here; the return value is serialised to JSON
and written to Redis under ``iett:mapping:{YYYY-MM-DD}`` per spec §5.7.

Keeping the reshaping in a pure function means tests can check the shape
without fakeredis, and the refresh task stays a thin wrapper around
``fetch + build + redis.set``.
"""
from __future__ import annotations

import datetime
import logging
from collections import defaultdict

from apps.core.constants import METROBUS_ROUTES
from apps.realtime.schemas import IettArsivGorev

logger = logging.getLogger(__name__)


def build_mapping(
    records: list[IettArsivGorev],
    date: datetime.date,
) -> dict:
    """Return the KapiNo → tasks mapping payload described in spec §5.7.

    Expected input: a list of ``IettArsivGorev`` that has already been
    filtered upstream (parser drops non-T status and null timestamps).
    This helper does not re-validate; it just reshapes.

    Per-KapiNo task lists are sorted by ``start_ms`` ascending so the
    fetch task's ``bisect_right`` lookup is O(log n).

    Output shape::

        {
            "date": "YYYY-MM-DD",
            "by_kapi": {
                "C-231": [
                    {"start_ms": int, "end_ms": int,
                     "hat": str, "guzergah": str},
                    ...
                ],
                ...
            },
            "active_routes": [...],        # sorted unique SHATKODU
            "routes_by_mode": {
                "metrobus": [...],         # METROBUS_ROUTES ∩ active
                "bus":      [...],         # active - METROBUS_ROUTES
            }
        }

    Other modes (metro/tram/funicular/marmaray/ferry) are absent by
    design — they don't come from the İETT feed. The consumer side
    merges them from the GTFS DB at request time.
    """
    by_kapi: dict[str, list[dict]] = defaultdict(list)
    active_routes: set[str] = set()

    empty_kapi_skipped = 0
    inverted_skipped = 0

    for rec in records:
        kapi = rec.kapi_no
        if not kapi:
            empty_kapi_skipped += 1
            continue

        start_ms = int(rec.start_time.timestamp() * 1000)
        end_ms = int(rec.end_time.timestamp() * 1000)
        if end_ms < start_ms:
            inverted_skipped += 1
            logger.warning(
                "build_mapping: inverted interval dropped "
                "(kapi=%s hat=%s start_ms=%d end_ms=%d)",
                kapi, rec.hat_kodu, start_ms, end_ms,
            )
            continue

        by_kapi[kapi].append({
            "start_ms": start_ms,
            "end_ms": end_ms,
            "hat": rec.hat_kodu,
            "guzergah": rec.guzergah_kodu,
        })
        active_routes.add(rec.hat_kodu)

    for kapi_tasks in by_kapi.values():
        kapi_tasks.sort(key=lambda t: t["start_ms"])

    metrobus_active = sorted(active_routes & METROBUS_ROUTES)
    bus_active = sorted(active_routes - METROBUS_ROUTES)

    if empty_kapi_skipped or inverted_skipped:
        logger.info(
            "build_mapping: total=%d kept=%d skipped=%d "
            "(empty_kapi=%d inverted=%d)",
            len(records),
            len(records) - empty_kapi_skipped - inverted_skipped,
            empty_kapi_skipped + inverted_skipped,
            empty_kapi_skipped, inverted_skipped,
        )

    return {
        "date": date.isoformat(),
        "by_kapi": dict(by_kapi),
        "active_routes": sorted(active_routes),
        "routes_by_mode": {
            "metrobus": metrobus_active,
            "bus": bus_active,
        },
    }
