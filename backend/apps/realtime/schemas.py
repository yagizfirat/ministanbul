"""Pydantic schemas for the realtime pipeline.

- VehiclePosition: per-vehicle snapshot emitted by every adapter
  (IETT SOAP, simulated metro, ferry, etc.) before it reaches the
  WebSocket and REST layers. Independent of upstream field names.
- IettArsivGorev: single record from ibb360.asmx::GetIettArsivGorev_json
  used to build the time-bound KapiNo → HatKodu mapping.
- parse_msdate: Microsoft JSON Date parser (/Date(ms)/ or /Date(ms+HHMM)/).
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, ConfigDict


_MSDATE_RE = re.compile(
    r"^/Date\((?P<ms>-?\d+)(?:(?P<sign>[+-])(?P<hh>\d{2})(?P<mm>\d{2}))?\)/$"
)


def parse_msdate(raw: str) -> datetime:
    """Parse Microsoft JSON date format into a timezone-aware datetime.

    Accepts both ``/Date(1776863726000)/`` (UTC implied) and
    ``/Date(1776863726000+0300)/`` (explicit offset). Raises ``ValueError``
    on any other shape. The absolute instant is always derived from the
    epoch milliseconds; the offset only changes the returned tzinfo.
    """
    m = _MSDATE_RE.match(raw)
    if m is None:
        raise ValueError(f"Invalid /Date(...)/ format: {raw!r}")

    ms = int(m.group("ms"))
    dt_utc = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)

    sign = m.group("sign")
    if sign is None:
        return dt_utc

    offset = timedelta(hours=int(m.group("hh")), minutes=int(m.group("mm")))
    if sign == "-":
        offset = -offset
    return dt_utc.astimezone(timezone(offset))


class VehiclePosition(BaseModel):
    """Canonical position snapshot emitted by every realtime adapter."""

    model_config = ConfigDict(frozen=True)

    vehicle_id: str
    route_id: str | None = None
    trip_id: str | None = None
    latitude: float
    longitude: float
    bearing: float | None = None
    speed: float | None = None
    timestamp: datetime
    source: str
    mode: str
    # Categorization flag for metrobüs vehicles, populated by enrich.py
    # via the same KapiNo mapping cache lookup. Independent of the
    # IETT_BUS_MAPPING_ENABLED flag — categorization is a side-effect
    # of the lookup and runs regardless. Defaults to False on cache miss.
    is_metrobus: bool = False


class IettArsivGorev(BaseModel):
    """Single record from ibb360.asmx::GetIettArsivGorev_json."""

    model_config = ConfigDict(frozen=True)

    kapi_no: str
    hat_kodu: str
    guzergah_kodu: str
    start_time: datetime
    end_time: datetime
    gorev_durum: str
