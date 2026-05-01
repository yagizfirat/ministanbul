"""Time helpers for Faz 5 trips_active endpoint.

Europe/Istanbul timezone is the project default; GTFS times are local
HH:MM:SS strings (may exceed 24h for overnight service).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

ISTANBUL = ZoneInfo("Europe/Istanbul")
WEEKDAY_FIELDS = (
    "monday", "tuesday", "wednesday", "thursday",
    "friday", "saturday", "sunday",
)


def now_istanbul() -> datetime:
    return datetime.now(ISTANBUL)


def parse_hhmmss(s: str) -> timedelta:
    """'14:23:00' or '25:30:00' (overnight) -> timedelta. Raises ValueError."""
    h, m, sec = s.split(":")
    return timedelta(hours=int(h), minutes=int(m), seconds=int(sec))


def seconds_since_midnight(dt: datetime) -> int:
    return dt.hour * 3600 + dt.minute * 60 + dt.second


def weekday_field(dt: datetime) -> str:
    """datetime -> 'monday'/'tuesday'/.../'sunday' (Calendar field name)."""
    return WEEKDAY_FIELDS[dt.weekday()]
