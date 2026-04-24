"""IETT SOAP adapter — fetches vehicle positions from api.ibb.gov.tr.

Phase 2 Step 4 owns this module. The wire shape is a SOAP envelope with
an entity-encoded JSON payload nested in a ``<{Method}Result>`` element
(spec Ek A.11.2). ``zeep`` cannot parse the WSDL, so we speak raw HTTP
and decode the body with ``xml.etree`` + ``json``.

This file exposes the pure parsers:

- ``_parse_arsiv_response``: ``GetIettArsivGorev_json`` → list[IettArsivGorev]
- ``_parse_fleet_response``: ``GetFiloAracKonum_json``  → list[VehiclePosition]

Skip policy: malformed or semantically-empty rows are dropped silently;
each parse emits **one** INFO summary line with per-reason counters so
ops can grep a single line, not N warnings. Live-log trends on e.g.
``null_end`` vs ``malformed`` then surface upstream data drift.

The ``IettSoapAdapter`` class (Step VI) wraps these parsers behind
rate-limit and distributed-lock gates.
"""
from __future__ import annotations

import json
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, time, timezone
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from apps.realtime.schemas import IettArsivGorev, VehiclePosition, parse_msdate

logger = logging.getLogger(__name__)

_SOAP_NS = {
    "soap": "http://schemas.xmlsoap.org/soap/envelope/",
    "t": "http://tempuri.org/",
}

_ISTANBUL_TZ = ZoneInfo("Europe/Istanbul")


def _extract_json_body(xml_body: str, result_tag: str) -> Any:
    """Pull the JSON payload out of a ``<{result_tag}>`` SOAP response.

    Returns the parsed JSON (usually a list). Raises ``ValueError`` if the
    expected element is missing or the payload is not valid JSON — the
    caller should treat that as an upstream-shape failure, not a skip.
    """
    root = ET.fromstring(xml_body)
    result_elem = root.find(f".//t:{result_tag}", _SOAP_NS)
    if result_elem is None:
        raise ValueError(f"SOAP body missing <{result_tag}> element")
    text = result_elem.text or "[]"
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"<{result_tag}> payload is not JSON: {exc}") from exc


def _parse_arsiv_response(xml_body: str) -> list[IettArsivGorev]:
    """Decode a GetIettArsivGorev_jsonResponse envelope to canonical records.

    Skip policy (silent; tallied in the summary INFO line):
      - ``SGOREVDURUM != "T"``             → ``non_T_status``
      - ``DTBASLAMAZAMANI`` null           → ``null_start``
      - ``DTBITISZAMANI`` null             → ``null_end``
      - any KeyError / ValueError / VE     → ``malformed``

    ``null_end`` is split out from ``malformed`` on purpose: an elevated
    ``null_end`` count in production points at unfinished tasks (data
    freshness lag), whereas ``malformed`` points at real upstream drift.
    """
    raw = _extract_json_body(xml_body, "GetIettArsivGorev_jsonResult")
    if not isinstance(raw, list):
        raise ValueError(
            f"GetIettArsivGorev_jsonResult: expected list, got {type(raw).__name__}"
        )

    total = len(raw)
    result: list[IettArsivGorev] = []
    non_T = 0
    null_start = 0
    null_end = 0
    malformed = 0

    for rec in raw:
        if rec.get("SGOREVDURUM") != "T":
            non_T += 1
            continue
        if rec.get("DTBASLAMAZAMANI") is None:
            null_start += 1
            continue
        if rec.get("DTBITISZAMANI") is None:
            null_end += 1
            continue
        try:
            result.append(
                IettArsivGorev(
                    kapi_no=rec["SKAPINUMARA"],
                    hat_kodu=rec["SHATKODU"],
                    guzergah_kodu=rec["SGUZERGAHKODU"],
                    start_time=parse_msdate(rec["DTBASLAMAZAMANI"]),
                    end_time=parse_msdate(rec["DTBITISZAMANI"]),
                    gorev_durum=rec["SGOREVDURUM"],
                )
            )
        except (KeyError, ValueError, ValidationError, TypeError):
            malformed += 1

    ok_count = len(result)
    skip_count = non_T + null_start + null_end + malformed
    logger.info(
        "arsiv_parse: total=%d ok=%d skipped=%d "
        "(non_T_status=%d null_start=%d null_end=%d malformed=%d)",
        total, ok_count, skip_count,
        non_T, null_start, null_end, malformed,
    )
    return result


def _parse_fleet_response(
    xml_body: str,
    at: datetime,
    source: str = "iett-soap",
    mode: str = "bus",
) -> list[VehiclePosition]:
    """Decode a GetFiloAracKonum_jsonResponse envelope to canonical positions.

    The upstream payload carries only ``Saat`` (``HH:MM:SS``), assumed to be
    Europe/Istanbul wall-clock time. We combine it with ``at``'s date in
    Istanbul local time to produce an aware datetime, then convert to UTC
    for ``VehiclePosition.timestamp``.

    TODO (Phase 6): handle the midnight-rollover edge case. If a vehicle
    stamps 23:59:50 and the adapter fetches seconds later at 00:00:05, the
    date we bind is *today* even though the vehicle's sample belongs to
    *yesterday*. For <1% of 60 s polls this is acceptable; the fix will
    compare parsed wall-clock against ``at`` and subtract a day when the
    gap exceeds a threshold.

    ``route_id`` is left ``None`` here — the Celery task enriches it from
    the time-bound KapiNo → HatKodu mapping (spec Ek A.14) after fetch.

    Skip policy (silent; tallied in the summary INFO line):
      - ``Boylam``/``Enlem`` not parseable as float → ``invalid_coord``
      - ``Hiz`` not parseable as float              → ``invalid_speed``
      - ``Saat`` not ``HH:MM:SS``                   → ``invalid_time``
      - any KeyError / ValidationError / etc.       → ``malformed``
    """
    raw = _extract_json_body(xml_body, "GetFiloAracKonum_jsonResult")
    if not isinstance(raw, list):
        raise ValueError(
            f"GetFiloAracKonum_jsonResult: expected list, got {type(raw).__name__}"
        )

    local_date = at.astimezone(_ISTANBUL_TZ).date()

    total = len(raw)
    result: list[VehiclePosition] = []
    invalid_coord = 0
    invalid_speed = 0
    invalid_time = 0
    malformed = 0

    for rec in raw:
        try:
            # Defensive: upstream has shipped "29,123" in prior captures
            # (research/test_filo_hatkodu_check.py) — normalise to dot.
            lat_raw = str(rec["Enlem"]).replace(",", ".")
            lon_raw = str(rec["Boylam"]).replace(",", ".")
            try:
                latitude = float(lat_raw)
                longitude = float(lon_raw)
            except (TypeError, ValueError):
                invalid_coord += 1
                continue

            try:
                speed = float(str(rec["Hiz"]).replace(",", "."))
            except (TypeError, ValueError):
                invalid_speed += 1
                continue

            try:
                t = time.fromisoformat(rec["Saat"])
            except (TypeError, ValueError):
                invalid_time += 1
                continue

            ts_local = datetime.combine(local_date, t, tzinfo=_ISTANBUL_TZ)
            timestamp = ts_local.astimezone(timezone.utc)

            result.append(
                VehiclePosition(
                    vehicle_id=rec["KapiNo"],
                    route_id=None,
                    trip_id=None,
                    latitude=latitude,
                    longitude=longitude,
                    bearing=None,
                    speed=speed,
                    timestamp=timestamp,
                    source=source,
                    mode=mode,
                )
            )
        except (KeyError, ValidationError, TypeError):
            malformed += 1

    ok_count = len(result)
    skip_count = invalid_coord + invalid_speed + invalid_time + malformed
    logger.info(
        "fleet_parse: total=%d ok=%d skipped=%d "
        "(invalid_coord=%d invalid_speed=%d invalid_time=%d malformed=%d)",
        total, ok_count, skip_count,
        invalid_coord, invalid_speed, invalid_time, malformed,
    )
    return result
