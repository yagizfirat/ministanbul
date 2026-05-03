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

Stale vehicle.timestamp filter (2026-05-02): when ``reference_now`` is
supplied, vehicles whose ``timestamp`` drifts more than
``STALE_VEHICLE_TIMESTAMP_THRESHOLD_S`` from it (in either direction)
are demoted to ``route_id=None`` even if the bisect found a matching
interval. Empirical motivation: İETT fleet endpoint can return a
multi-hour-old ``DTGUNCELLEMESAATI`` for idle/parked vehicles — bisect
lands on the OLD active interval and stamps an outdated PK. Threshold
180s sits 3× the nominal 60 s tick, comfortably above the 0–60 s
mikro-tick band observed in the diagnostic histogram.
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

    # v0.8.0 (KM5-a): IETT bus mapping retire (Spec §5.7, Ek A.18 R12).
    # Flag default kapalı; tüm İETT bus için route_id=None, drift filter
    # de tetiklenmez (route_id None ⇒ stale check zaten skip). Hibernation
    # path (flag açık) aşağıda aynen korunur, gelecekte İBB veri kalitesi
    # düzelirse tek satırlık reaktivasyon.
    if not settings.IETT_BUS_MAPPING_ENABLED:
        return [v.model_copy(update={"route_id": None}) for v in vehicles], 0

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
    stale_dropped = 0
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

        if route_id is not None and reference_now is not None:
            drift = abs((reference_now - v.timestamp).total_seconds())
            if drift > STALE_VEHICLE_TIMESTAMP_THRESHOLD_S:
                route_id = None
                stale_dropped += 1

        out.append(v.model_copy(update={"route_id": route_id}))
    return out, stale_dropped
