"""Query helpers for /api/trips/active/.

The naïve aggregation relies on the (trip_id, stop_sequence) composite
index defined on stop_times.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from django.db.models import Max, Min

from apps.gtfs.models import Calendar, Trip
from apps.gtfs.timeutils import seconds_since_midnight, weekday_field

PUBLIC_PREFIX = "public:"

# Discovery raporu Ek Keşif Tablo C (2026-05-01).
# `route_type=1` (subway) Marmaray + diğer M-hatlarını paylaşır;
# ayrım short_name prefix'iyle yapılır.
MODE_FILTER: dict[str, dict] = {
    "metro":     {"route_type": [1], "exclude_short_prefix": "Marmaray"},
    "marmaray":  {"route_type": [1], "include_short_prefix": "Marmaray"},
    "tram":      {"route_type": [0]},
    "funicular": {"route_type": [7]},
    "ferry":     {"route_type": [4]},
}


def active_service_ids(now_dt: datetime) -> list[str]:
    """Calendar service_ids active for now_dt's weekday.

    Date-range filter (start_date/end_date) is intentionally bypassed —
    public feed end_date=20241231 is stale on İBB's side (verified via
    download_gtfs hash match, see discovery follow-up §A).
    """
    field = weekday_field(now_dt)
    return list(
        Calendar.objects.filter(**{field: True}).values_list("service_id", flat=True)
    )


def active_trips_query(mode: str, now_dt: datetime):
    """Trips of the given mode whose first→last arrival window covers now_dt.

    Window check uses MIN/MAX(arrival_time) aggregations — no denormalized
    columns yet (Faz 5 KM2-perf borç notu if measured >500ms).
    """
    cfg = MODE_FILTER[mode]
    now_td = timedelta(seconds=seconds_since_midnight(now_dt))

    qs = Trip.objects.filter(
        route__route_id__startswith=PUBLIC_PREFIX,
        route__route_type__in=cfg["route_type"],
        service_id__in=active_service_ids(now_dt),
    )
    if cfg.get("include_short_prefix"):
        qs = qs.filter(route__short_name__istartswith=cfg["include_short_prefix"])
    elif cfg.get("exclude_short_prefix"):
        qs = qs.exclude(route__short_name__istartswith=cfg["exclude_short_prefix"])

    qs = qs.annotate(
        _first_arr=Min("stop_times__arrival_time"),
        _last_arr=Max("stop_times__arrival_time"),
    ).filter(_first_arr__lte=now_td, _last_arr__gte=now_td)
    return qs
