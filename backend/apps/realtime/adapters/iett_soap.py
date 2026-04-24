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
from datetime import date, datetime, time, timezone
from typing import Any
from zoneinfo import ZoneInfo

import requests
from pydantic import ValidationError

from apps.realtime.adapters.base import BaseAdapter
from apps.realtime.locks import LockAcquisitionError, distributed_lock
from apps.realtime.rate_limit import LimitStatus
from apps.realtime.schemas import IettArsivGorev, VehiclePosition, parse_msdate

logger = logging.getLogger(__name__)

_SOAP_NS = {
    "soap": "http://schemas.xmlsoap.org/soap/envelope/",
    "t": "http://tempuri.org/",
}

_ISTANBUL_TZ = ZoneInfo("Europe/Istanbul")

FLEET_URL = "https://api.ibb.gov.tr/iett/FiloDurum/SeferGerceklesme.asmx"
ARSIV_URL = "https://api.ibb.gov.tr/iett/ibb/ibb360.asmx"

_FLEET_SOAP_ACTION = "http://tempuri.org/GetFiloAracKonum_json"
_ARSIV_SOAP_ACTION = "http://tempuri.org/GetIettArsivGorev_json"

_FLEET_ENVELOPE = (
    '<?xml version="1.0" encoding="utf-8"?>\n'
    '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">\n'
    "  <soap:Body>\n"
    '    <GetFiloAracKonum_json xmlns="http://tempuri.org/" />\n'
    "  </soap:Body>\n"
    "</soap:Envelope>\n"
)

_ARSIV_ENVELOPE_TEMPLATE = (
    '<?xml version="1.0" encoding="utf-8"?>\n'
    '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">\n'
    "  <soap:Body>\n"
    '    <GetIettArsivGorev_json xmlns="http://tempuri.org/">\n'
    "      <Tarih>{tarih}</Tarih>\n"
    "    </GetIettArsivGorev_json>\n"
    "  </soap:Body>\n"
    "</soap:Envelope>\n"
)

_TIMEOUT = (10, 60)  # (connect, read)
_POLICY_FALSIFIED_MARKER = "Policy Falsified"


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


class IettRateLimitViolation(Exception):
    """HTTP 500 + 'Policy Falsified' body — gateway enforcement hit.

    Raising this signals that the shared rate-limit cooldown has been
    armed. The caller should not retry until ``limiter.in_cooldown()``
    clears (default 30 minutes per spec Ek A.11).
    """


class IettSoapAdapter(BaseAdapter):
    """Adapter that feeds VehiclePosition from the IETT SOAP endpoint.

    Each fetch is gated twice:
      1. A process-shared ``SlidingWindowLimiter`` short-circuits on
         ``BLOCKED``/``COOLDOWN`` so we stop the request before it hits
         the gateway (avoids stacking violations during an incident).
      2. A Redis ``distributed_lock`` ensures only one Celery worker
         fires the request per cadence tick — parallel workers politely
         skip and try again next tick.

    A 500 whose body contains ``Policy Falsified`` is treated as the
    gateway explicitly rate-limiting us: we record a violation (which
    arms the cooldown) and raise :class:`IettRateLimitViolation`. All
    other non-2xx responses raise ``requests.HTTPError`` without
    touching the cooldown — the upstream may just be flaky.
    """

    name = "iett-soap"
    source = "iett-soap"
    mode = "bus"

    def __init__(
        self,
        redis_client,
        fleet_limiter,
        arsiv_limiter,
        session: requests.Session | None = None,
    ) -> None:
        self._redis = redis_client
        self._fleet_limiter = fleet_limiter
        self._arsiv_limiter = arsiv_limiter
        self._session = session or requests.Session()

    def _post(
        self,
        url: str,
        envelope: str,
        soap_action: str,
        limiter,
        lock_key: str,
    ) -> str | None:
        """Shared request flow. Returns response.text, or None if skipped.

        None means the call was not attempted (limiter BLOCKED/COOLDOWN
        or another worker holds the lock). The caller should treat None
        as "empty snapshot, try again next tick".

        Raises :class:`IettRateLimitViolation` on 500 + Policy Falsified.
        Raises ``requests.HTTPError`` on any other non-2xx.
        """
        status = limiter.check()
        if status in (LimitStatus.BLOCKED, LimitStatus.COOLDOWN):
            logger.warning("skip %s: rate limit %s", lock_key, status.name)
            return None

        try:
            with distributed_lock(self._redis, lock_key, timeout_seconds=30):
                response = self._session.post(
                    url,
                    data=envelope.encode("utf-8"),
                    headers={
                        "Content-Type": "text/xml; charset=utf-8",
                        "SOAPAction": f'"{soap_action}"',
                    },
                    timeout=_TIMEOUT,
                )
        except LockAcquisitionError:
            logger.warning("skip %s: lock held by another worker", lock_key)
            return None

        if (
            response.status_code == 500
            and _POLICY_FALSIFIED_MARKER in response.text
        ):
            limiter.record_violation()
            raise IettRateLimitViolation(
                f"{url}: HTTP 500 Policy Falsified (cooldown armed)"
            )

        response.raise_for_status()
        limiter.record_call()
        return response.text

    def fetch(self) -> list[VehiclePosition]:
        text = self._post(
            FLEET_URL,
            _FLEET_ENVELOPE,
            _FLEET_SOAP_ACTION,
            self._fleet_limiter,
            "iett_fetch_fleet",
        )
        if text is None:
            return []
        return _parse_fleet_response(text, at=datetime.now(tz=timezone.utc))

    def fetch_arsiv_gorev(self, target_date: date) -> list[IettArsivGorev]:
        envelope = _ARSIV_ENVELOPE_TEMPLATE.format(
            tarih=target_date.strftime("%Y%m%d")
        )
        text = self._post(
            ARSIV_URL,
            envelope,
            _ARSIV_SOAP_ACTION,
            self._arsiv_limiter,
            "iett_fetch_arsiv",
        )
        if text is None:
            return []
        return _parse_arsiv_response(text)

    def health(self) -> dict:
        return {
            "adapter": self.name,
            "fleet_limiter": self._fleet_limiter.status_snapshot(),
            "arsiv_limiter": self._arsiv_limiter.status_snapshot(),
        }
