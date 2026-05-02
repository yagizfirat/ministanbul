"""KapiNo + timestamp lookup that stamps ``route_id`` onto vehicle snapshots.

Pure consumer of the mapping payload built by ``apps.realtime.mapping``
and cached in Redis under ``iett:mapping:current`` (spec §5.7). This
helper does not touch Redis itself — the fetch task (Adım 5d) decodes
the JSON and hands it in as a plain dict.

Phase 2 Step 5i-ii refactor: payloads now use wall-clock seconds
(Istanbul TZ) keyed by ``snapshot_date`` / ``snapshot_day_type``.
Lookup is ``bisect_right`` over the per-KapiNo ``start_sec`` list, so
the algorithm is O(log n) per vehicle. End is inclusive; vehicles whose
KapiNo is missing from the mapping or whose wall-clock seconds fall
into a gap between intervals come out with ``route_id=None``.

Per-vehicle overnight detection: a vehicle whose local timestamp lies
on the day after ``snapshot_date`` AND before 04:00 falls into the
extended interval range (``end_sec >= 86400``); its ``now_sec`` is
shifted by 86400 so the bisect lands on the right interval.

Overlap convention (spec §5.7 + ROADMAP 5c): when two intervals cover
the same instant the later-starting one wins, which is what
``bisect_right - 1`` naturally returns.

Mismatch detection (today_dt != snapshot_day_type AND not overnight)
lives in ``tasks.py::fetch_iett_positions`` — this function stays a
pure best-effort lookup and never short-circuits the loop.
"""
from __future__ import annotations

from bisect import bisect_right
from datetime import date, timedelta

from apps.realtime.calendar import ISTANBUL_TZ
from apps.realtime.schemas import VehiclePosition


def enrich_with_route_id(
    vehicles: list[VehiclePosition],
    mapping: dict,
) -> list[VehiclePosition]:
    """Return new ``VehiclePosition`` objects with ``route_id`` resolved.

    Pure function: input list and elements are not mutated. Each output
    element is a pydantic v2 ``model_copy(update={"route_id": ...})`` of
    its input.

    Vehicles whose KapiNo is absent from ``mapping["by_kapi"]`` or whose
    timestamp lies outside every cached interval pass through with
    ``route_id=None``. Counting unmapped vehicles is the caller's job
    (the fetch task records it as a stat).
    """
    if not vehicles:
        return []

    by_kapi = mapping.get("by_kapi", {})
    pk_index = mapping.get("route_id_by_short_name", {})
    snapshot_date_str = mapping.get("snapshot_date")
    snapshot_next_date: date | None = None
    if snapshot_date_str is not None:
        try:
            snapshot_next_date = (
                date.fromisoformat(snapshot_date_str) + timedelta(days=1)
            )
        except ValueError:
            snapshot_next_date = None

    out: list[VehiclePosition] = []
    for v in vehicles:
        intervals = by_kapi.get(v.vehicle_id)
        route_id: str | None = None
        if intervals:
            local = v.timestamp.astimezone(ISTANBUL_TZ)
            base_sec = local.hour * 3600 + local.minute * 60 + local.second

            # Per-vehicle overnight check: vehicle date is exactly the day
            # AFTER snapshot_date AND before 04:00 → look in extended range.
            # Date-based comparison (not day_type) avoids false positives
            # when snapshot_day_type and next_day_type happen to coincide
            # (e.g. Wed snapshot + Thu vehicle, both "weekday").
            is_overnight = (
                snapshot_next_date is not None
                and local.date() == snapshot_next_date
                and local.hour < 4
            )
            now_sec = base_sec + 86400 if is_overnight else base_sec

            starts = [iv["start_sec"] for iv in intervals]
            idx = bisect_right(starts, now_sec) - 1
            if idx >= 0 and now_sec <= intervals[idx]["end_sec"]:
                # Yol B: translate SHATKODU → GTFS Route.route_id PK so the
                # frontend's RouteStore (keyed by route_id) matches. Lookup
                # miss → None (orphan SHATKODU stays unmapped, graceful).
                route_id = pk_index.get(intervals[idx]["hat"])
        out.append(v.model_copy(update={"route_id": route_id}))
    return out
