"""Pydantic schemas for the realtime pipeline — Phase 2 Step 2.

Canonical schemas that flow through the pipeline:

- VehiclePosition: per-vehicle snapshot yielded by every adapter
  (IETT SOAP, simulated metro, ferry, etc.) before it hits the WebSocket
  and REST layers. Independent of upstream field names (spec §5.3).
- IettArsivGorev: single record from ibb360.asmx::GetIettArsivGorev_json,
  used to build the time-bound KapiNo → HatKodu mapping
  (spec Ek A.13, A.14).

Helpers:
- parse_msdate: Microsoft JSON Date parser (/Date(ms)/ or /Date(ms+HHMM)/).

Adapter implementations, tasks and the rate limiter land in Steps 3–5.
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
    """Canonical position snapshot emitted by every realtime adapter (spec §5.3)."""

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
    # KM5-e.1 (Spec §3.3): metrobüs kategorize sinyali — frontend antrasit
    # gri rendering ayrımı için. enrich.py mapping cache lookup'ı her iki
    # IETT_BUS_MAPPING_ENABLED durumunda yapar; route_id stampleme flag'a
    # bağlı, is_metrobus değil. Mapping cache miss → False (defansif).
    # %22 yanlış kategori riski Yağız kararı (B yolundan dönüş): rengin
    # yokluğu = %0 bilgi, varlığı yanlışlık olsa bile %78 doğru.
    is_metrobus: bool = False


class IettArsivGorev(BaseModel):
    """Single record from ibb360.asmx::GetIettArsivGorev_json (spec Ek A.14)."""

    model_config = ConfigDict(frozen=True)

    kapi_no: str
    hat_kodu: str
    guzergah_kodu: str
    start_time: datetime
    end_time: datetime
    gorev_durum: str
