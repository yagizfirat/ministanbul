"""KapiNo + timestamp lookup that stamps ``route_id`` onto vehicle snapshots.

Pure consumer of the mapping payload built by ``apps.realtime.mapping``
and cached in Redis under ``iett:mapping:current``. This helper does
not touch Redis itself — the fetch task decodes the JSON and hands it
in as a plain dict.

Lookup is ``bisect_right`` over a per-KapiNo list of (start_sec, end_sec)
intervals keyed by Istanbul wall-clock seconds — O(log n) per vehicle.
End is inclusive. Vehicles whose KapiNo isn't in the mapping, or whose
wall-clock seconds fall into a gap between intervals, come back with
``route_id=None``.

Per-vehicle overnight detection: when the vehicle's local timestamp
lies on the day after ``snapshot_date`` AND before 04:00, ``now_sec``
is shifted by 86400 so the bisect lands inside the corresponding
extended-range interval (those have ``end_sec >= 86400``).

Overlap convention: when two intervals cover the same instant the
later-starting one wins — which is exactly what ``bisect_right - 1``
returns.

Stale-timestamp filter: when ``reference_now`` is supplied, vehicles
whose timestamp drifts more than ``STALE_VEHICLE_TIMESTAMP_THRESHOLD_S``
from it (either direction) are demoted to ``route_id=None`` even when
the bisect found a matching interval. Motivation: İETT's fleet endpoint
can serve multi-hour-old ``DTGUNCELLEMESAATI`` for idle/parked vehicles,
which would otherwise stamp an outdated PK. Threshold of 180s sits 3×
the nominal 60 s tick.
"""
from __future__ import annotations

from bisect import bisect_right
from datetime import date, datetime, timedelta

from django.conf import settings

from apps.realtime.calendar import ISTANBUL_TZ
from apps.realtime.schemas import VehiclePosition

STALE_VEHICLE_TIMESTAMP_THRESHOLD_S = 180


def enrich_with_route_id(
    vehicles: list[VehiclePosition],
    mapping: dict,
    *,
    reference_now: datetime | None = None,
) -> tuple[list[VehiclePosition], int]:
    """Return ``(enriched_vehicles, stale_dropped_count)``.

    Pure function: input list and elements are not mutated. Each output
    element is a pydantic v2 ``model_copy(update={"route_id": ...})`` of
    its input.

    Vehicles whose KapiNo is absent from ``mapping["by_kapi"]`` or whose
    timestamp lies outside every cached interval pass through with
    ``route_id=None``. Counting unmapped vehicles is the caller's job
    (the fetch task records it as a stat).

    When ``reference_now`` is supplied, an extra stale-timestamp check
    runs after the bisect: any vehicle that *would* have been stamped
    but whose timestamp drifts more than
    ``STALE_VEHICLE_TIMESTAMP_THRESHOLD_S`` (abs, two-sided) from
    ``reference_now`` is demoted to ``route_id=None`` and counted in
    ``stale_dropped_count``. ``reference_now=None`` (default) disables
    the check and always returns ``stale_dropped_count=0`` — preserves
    the pre-2026-05-02 contract for existing callers and tests.
    """
    if not vehicles:
        return [], 0

    by_kapi = mapping.get("by_kapi", {})
    snapshot_next_date = _snapshot_next_date(mapping)

    # The İETT bus mapping is hibernated by default
    # (settings.IETT_BUS_MAPPING_ENABLED=False) — every bus gets
    # route_id=None and the stale-timestamp filter is skipped (route_id
    # is None anyway). The cache is still consulted for is_metrobus
    # categorization, which is a free side-effect of the same lookup.
    # If İBB data quality improves, flipping the flag re-enables the
    # mapping path below unchanged.
    if not settings.IETT_BUS_MAPPING_ENABLED:
        out: list[VehiclePosition] = []
        for v in vehicles:
            hat = _resolve_active_hat(v, by_kapi, snapshot_next_date)
            is_metrobus = bool(hat and hat in settings.METROBUS_SHORT_NAMES)
            out.append(v.model_copy(update={
                "route_id": None,
                "is_metrobus": is_metrobus,
            }))
        return out, 0

    pk_index = mapping.get("route_id_by_short_name", {})

    out = []
    stale_dropped = 0
    for v in vehicles:
        hat = _resolve_active_hat(v, by_kapi, snapshot_next_date)
        # Translate SHATKODU → GTFS Route.route_id PK so the frontend's
        # RouteStore (keyed by route_id) matches. An orphan SHATKODU
        # not in the index stays unmapped (None), which is graceful.
        route_id = pk_index.get(hat) if hat is not None else None
        is_metrobus = bool(hat and hat in settings.METROBUS_SHORT_NAMES)

        if route_id is not None and reference_now is not None:
            drift = abs((reference_now - v.timestamp).total_seconds())
            if drift > STALE_VEHICLE_TIMESTAMP_THRESHOLD_S:
                route_id = None
                stale_dropped += 1

        out.append(v.model_copy(update={
            "route_id": route_id,
            "is_metrobus": is_metrobus,
        }))
    return out, stale_dropped


def _snapshot_next_date(mapping: dict) -> date | None:
    """The day after the mapping snapshot — used for overnight bisect bumps."""
    snapshot_date_str = mapping.get("snapshot_date")
    if snapshot_date_str is None:
        return None
    try:
        return date.fromisoformat(snapshot_date_str) + timedelta(days=1)
    except ValueError:
        return None


def _resolve_active_hat(
    vehicle: VehiclePosition,
    by_kapi: dict,
    snapshot_next_date: date | None,
) -> str | None:
    """KapiNo + timestamp → the SHATKODU active at that moment, or None.

    Pure helper — same bisect path is used by both the route_id-stamping
    branch and the is_metrobus-categorization branch. Doesn't touch
    settings/DB/Redis (whitelist checks live at the caller).

    Per-vehicle overnight check: when the vehicle's local date is
    exactly the day AFTER snapshot_date and the hour is before 04:00,
    we look up the extended range. Comparing dates (rather than day
    types) avoids false positives when snapshot_day_type and the next
    day's type coincide (e.g. Wed/Thu both "weekday").
    """
    intervals = by_kapi.get(vehicle.vehicle_id)
    if not intervals:
        return None
    local = vehicle.timestamp.astimezone(ISTANBUL_TZ)
    base_sec = local.hour * 3600 + local.minute * 60 + local.second
    is_overnight = (
        snapshot_next_date is not None
        and local.date() == snapshot_next_date
        and local.hour < 4
    )
    now_sec = base_sec + 86400 if is_overnight else base_sec

    starts = [iv["start_sec"] for iv in intervals]
    idx = bisect_right(starts, now_sec) - 1
    if idx >= 0 and now_sec <= intervals[idx]["end_sec"]:
        return intervals[idx]["hat"]
    return None
