"""KapiNo + timestamp lookup that stamps ``route_id`` onto vehicle snapshots.

Pure consumer of the mapping payload built by ``apps.realtime.mapping``
and cached in Redis under ``iett:mapping:{YYYY-MM-DD}`` (spec §5.7). This
helper does not touch Redis itself — the fetch task (Adım 5d) decodes
the JSON and hands it in as a plain dict.

Lookup is ``bisect_right`` over the per-KapiNo ``start_ms`` list, so the
algorithm is O(log n) per vehicle. End is inclusive; vehicles whose
KapiNo is missing from the mapping or whose timestamp falls into a gap
between intervals come out with ``route_id=None``. Overlap convention
(spec §5.7 + ROADMAP 5c): when two intervals cover the same instant the
later-starting one wins, which is what ``bisect_right - 1`` naturally
returns.
"""
from __future__ import annotations

from bisect import bisect_right

from apps.realtime.schemas import VehiclePosition


def enrich_with_route_id(
    vehicles: list[VehiclePosition],
    mapping: dict,
) -> list[VehiclePosition]:
    """Return new ``VehiclePosition`` objects with ``route_id`` resolved.

    Pure function: the input list and its elements are not mutated.
    Each output element is a pydantic v2
    ``model_copy(update={"route_id": ...})`` of its input.

    Vehicles whose KapiNo is absent from ``mapping["by_kapi"]`` or whose
    ``timestamp`` lies outside every cached interval pass through with
    ``route_id=None``. Counting unmapped vehicles is the caller's job
    (the fetch task records it as a stat).
    """
    by_kapi = mapping.get("by_kapi", {})
    out: list[VehiclePosition] = []
    for v in vehicles:
        intervals = by_kapi.get(v.vehicle_id)
        route_id: str | None = None
        if intervals:
            now_ms = int(v.timestamp.timestamp() * 1000)
            starts = [iv["start_ms"] for iv in intervals]
            idx = bisect_right(starts, now_ms) - 1
            if idx >= 0 and now_ms <= intervals[idx]["end_ms"]:
                route_id = intervals[idx]["hat"]
        out.append(v.model_copy(update={"route_id": route_id}))
    return out
