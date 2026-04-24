"""Tests for the IETT SOAP parsers and (later) adapter.

Cassettes in ``cassettes/`` replay real SOAP envelopes captured from
api.ibb.gov.tr during Phase 1.5 / 2 research. We mock the HTTP layer
and feed the XML string to the parsers directly so the parsing contract
is exercised without the network.
"""
from __future__ import annotations

import json
import logging
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from apps.realtime.adapters.iett_soap import (
    _parse_arsiv_response,
    _parse_fleet_response,
)

CASSETTES = Path(__file__).parent / "cassettes"
LOGGER_NAME = "apps.realtime.adapters.iett_soap"
_ISTANBUL_TZ = ZoneInfo("Europe/Istanbul")

_ARSIV_SUMMARY_RE = re.compile(
    r"arsiv_parse: total=(?P<total>\d+) ok=(?P<ok>\d+) skipped=(?P<skipped>\d+) "
    r"\(non_T_status=(?P<non_T_status>\d+) "
    r"null_start=(?P<null_start>\d+) "
    r"null_end=(?P<null_end>\d+) "
    r"malformed=(?P<malformed>\d+)\)"
)

_FLEET_SUMMARY_RE = re.compile(
    r"fleet_parse: total=(?P<total>\d+) ok=(?P<ok>\d+) skipped=(?P<skipped>\d+) "
    r"\(invalid_coord=(?P<invalid_coord>\d+) "
    r"invalid_speed=(?P<invalid_speed>\d+) "
    r"invalid_time=(?P<invalid_time>\d+) "
    r"malformed=(?P<malformed>\d+)\)"
)


def _entity_encode(raw: str) -> str:
    # Mirror the gateway: JSON body embedded as XML text is entity-escaped.
    return (
        raw.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _wrap_envelope(method: str, body: str) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">\n'
        "  <soap:Body>\n"
        f'    <{method}Response xmlns="http://tempuri.org/">\n'
        f"      <{method}Result>{_entity_encode(body)}</{method}Result>\n"
        f"    </{method}Response>\n"
        "  </soap:Body>\n"
        "</soap:Envelope>\n"
    )


@pytest.fixture
def arsiv_ok_body() -> str:
    return (CASSETTES / "arsiv_gorev_20260422_ok.xml").read_text(encoding="utf-8")


@pytest.fixture
def arsiv_empty_body() -> str:
    return (CASSETTES / "arsiv_gorev_empty_today.xml").read_text(encoding="utf-8")


@pytest.fixture
def filo_fetch_body() -> str:
    return (CASSETTES / "filo_fetch_ok.xml").read_text(encoding="utf-8")


def _extract_summary(
    caplog: pytest.LogCaptureFixture, pattern: re.Pattern[str]
) -> dict[str, int]:
    matches = [
        m for rec in caplog.records
        if (m := pattern.search(rec.getMessage()))
    ]
    assert len(matches) == 1, (
        f"expected exactly one summary line, got {len(matches)} "
        f"in {[r.getMessage() for r in caplog.records]}"
    )
    return {k: int(v) for k, v in matches[0].groupdict().items()}


def _cassette_raw_records(xml_body: str, result_tag: str) -> list[dict]:
    root = ET.fromstring(xml_body)
    elem = root.find(f".//{{http://tempuri.org/}}{result_tag}")
    assert elem is not None and elem.text is not None
    return json.loads(elem.text)


# --------------------------- arsiv parser tests ---------------------------


def test_parse_arsiv_happy_path(arsiv_ok_body, caplog):
    raw = _cassette_raw_records(arsiv_ok_body, "GetIettArsivGorev_jsonResult")
    total = len(raw)
    expected_non_T = sum(1 for r in raw if r["SGOREVDURUM"] != "T")
    expected_null_start = sum(
        1 for r in raw
        if r["SGOREVDURUM"] == "T" and r["DTBASLAMAZAMANI"] is None
    )
    expected_null_end = sum(
        1 for r in raw
        if r["SGOREVDURUM"] == "T"
        and r["DTBASLAMAZAMANI"] is not None
        and r["DTBITISZAMANI"] is None
    )

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        result = _parse_arsiv_response(arsiv_ok_body)

    summary = _extract_summary(caplog, _ARSIV_SUMMARY_RE)
    assert summary["total"] == total
    assert summary["non_T_status"] == expected_non_T
    assert summary["null_start"] == expected_null_start
    assert summary["null_end"] == expected_null_end
    assert summary["ok"] == len(result)
    assert (
        summary["skipped"]
        == summary["non_T_status"] + summary["null_start"]
        + summary["null_end"] + summary["malformed"]
    )
    assert summary["ok"] + summary["skipped"] == summary["total"]
    assert all(r.gorev_durum == "T" for r in result)


def test_parse_arsiv_empty(arsiv_empty_body, caplog):
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        result = _parse_arsiv_response(arsiv_empty_body)

    assert result == []
    summary = _extract_summary(caplog, _ARSIV_SUMMARY_RE)
    assert summary == {
        "total": 0, "ok": 0, "skipped": 0,
        "non_T_status": 0, "null_start": 0, "null_end": 0, "malformed": 0,
    }


def test_parse_arsiv_filters_non_T_silently(arsiv_ok_body, caplog):
    raw = _cassette_raw_records(arsiv_ok_body, "GetIettArsivGorev_jsonResult")
    expected_non_T = sum(1 for r in raw if r["SGOREVDURUM"] != "T")
    assert expected_non_T > 0, "cassette should contain at least one non-T record"

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        result = _parse_arsiv_response(arsiv_ok_body)

    # No WARN/ERROR per skipped record — just one INFO summary.
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert all(r.gorev_durum == "T" for r in result)
    summary = _extract_summary(caplog, _ARSIV_SUMMARY_RE)
    assert summary["non_T_status"] == expected_non_T


def test_parse_arsiv_handles_null_timestamps(arsiv_ok_body, caplog):
    raw = _cassette_raw_records(arsiv_ok_body, "GetIettArsivGorev_jsonResult")
    expected_null_start = sum(
        1 for r in raw
        if r["SGOREVDURUM"] == "T" and r["DTBASLAMAZAMANI"] is None
    )
    expected_null_end = sum(
        1 for r in raw
        if r["SGOREVDURUM"] == "T"
        and r["DTBASLAMAZAMANI"] is not None
        and r["DTBITISZAMANI"] is None
    )
    assert expected_null_start >= 1, (
        "stratified cassette lost its null-start T coverage"
    )

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        _parse_arsiv_response(arsiv_ok_body)

    summary = _extract_summary(caplog, _ARSIV_SUMMARY_RE)
    assert summary["null_start"] == expected_null_start
    assert summary["null_end"] == expected_null_end


def test_parse_arsiv_malformed_record_caught(caplog):
    # Four records: ok, bad msdate (malformed), missing SKAPINUMARA
    # (malformed), null end (null_end). Exercises all three skip reasons
    # plus the ok path.
    synthetic = [
        {
            "SHATKODU": "15SK", "SGUZERGAHKODU": "15SK_G_D0",
            "SKAPINUMARA": "M1000",
            "DTBASLAMAZAMANI": "/Date(1776863726000)/",
            "DTBITISZAMANI": "/Date(1776868886000)/",
            "SGOREVDURUM": "T",
        },
        {
            "SHATKODU": "15SK", "SGUZERGAHKODU": "15SK_G_D0",
            "SKAPINUMARA": "M1001",
            "DTBASLAMAZAMANI": "/Date(xyz)/",
            "DTBITISZAMANI": "/Date(1776868886000)/",
            "SGOREVDURUM": "T",
        },
        {
            "SHATKODU": "15SK", "SGUZERGAHKODU": "15SK_G_D0",
            # SKAPINUMARA missing
            "DTBASLAMAZAMANI": "/Date(1776863726000)/",
            "DTBITISZAMANI": "/Date(1776868886000)/",
            "SGOREVDURUM": "T",
        },
        {
            "SHATKODU": "15SK", "SGUZERGAHKODU": "15SK_G_D0",
            "SKAPINUMARA": "M1003",
            "DTBASLAMAZAMANI": "/Date(1776863726000)/",
            "DTBITISZAMANI": None,
            "SGOREVDURUM": "T",
        },
    ]
    envelope = _wrap_envelope(
        "GetIettArsivGorev_json", json.dumps(synthetic, ensure_ascii=False)
    )

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        result = _parse_arsiv_response(envelope)

    assert len(result) == 1
    assert result[0].kapi_no == "M1000"
    summary = _extract_summary(caplog, _ARSIV_SUMMARY_RE)
    assert summary["total"] == 4
    assert summary["ok"] == 1
    assert summary["non_T_status"] == 0
    assert summary["null_start"] == 0
    assert summary["null_end"] == 1
    assert summary["malformed"] == 2


# --------------------------- fleet parser tests ---------------------------


@pytest.fixture
def fleet_at() -> datetime:
    # Picked so every cassette HH:MM:SS (all on 2026-04-22 evening Istanbul)
    # resolves to a sensible wall-clock on 2026-04-22.
    return datetime(2026, 4, 22, 17, 30, tzinfo=timezone.utc)


def test_parse_fleet_happy_path(filo_fetch_body, fleet_at, caplog):
    raw = _cassette_raw_records(filo_fetch_body, "GetFiloAracKonum_jsonResult")
    assert len(raw) == 12  # sanity: cassette shape matches Step III expectation

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        result = _parse_fleet_response(filo_fetch_body, at=fleet_at)

    assert len(result) == 12
    first = result[0]
    raw_first = raw[0]
    assert first.vehicle_id == raw_first["KapiNo"]
    assert first.source == "iett-soap"
    assert first.mode == "bus"
    assert first.route_id is None
    assert first.trip_id is None
    assert first.bearing is None
    assert first.latitude == pytest.approx(float(raw_first["Enlem"]))
    assert first.longitude == pytest.approx(float(raw_first["Boylam"]))
    assert first.speed == pytest.approx(float(raw_first["Hiz"]))
    assert first.timestamp.tzinfo is not None
    assert first.timestamp.utcoffset().total_seconds() == 0

    summary = _extract_summary(caplog, _FLEET_SUMMARY_RE)
    assert summary == {
        "total": 12, "ok": 12, "skipped": 0,
        "invalid_coord": 0, "invalid_speed": 0,
        "invalid_time": 0, "malformed": 0,
    }


def test_parse_fleet_empty(fleet_at, caplog):
    envelope = _wrap_envelope("GetFiloAracKonum_json", "[]")
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        result = _parse_fleet_response(envelope, at=fleet_at)

    assert result == []
    summary = _extract_summary(caplog, _FLEET_SUMMARY_RE)
    assert summary == {
        "total": 0, "ok": 0, "skipped": 0,
        "invalid_coord": 0, "invalid_speed": 0,
        "invalid_time": 0, "malformed": 0,
    }


def test_parse_fleet_at_parameter_determinism(filo_fetch_body):
    # Two `at` values on different Istanbul-local dates. The parser binds
    # the Saat to `at`'s local date, so the resulting UTC timestamp must
    # shift by exactly one day.
    at1 = datetime(2026, 4, 22, 10, 0, tzinfo=timezone.utc)  # Istanbul 2026-04-22
    at2 = datetime(2026, 4, 23, 10, 0, tzinfo=timezone.utc)  # Istanbul 2026-04-23

    r1 = _parse_fleet_response(filo_fetch_body, at=at1)
    r2 = _parse_fleet_response(filo_fetch_body, at=at2)

    assert len(r1) == len(r2) == 12
    for v1, v2 in zip(r1, r2):
        assert v1.vehicle_id == v2.vehicle_id
        # Same wall-clock Saat, one day apart.
        assert (v2.timestamp - v1.timestamp).total_seconds() == 86400
        # Local date should match `at`'s Istanbul date.
        assert v1.timestamp.astimezone(_ISTANBUL_TZ).date() == date(2026, 4, 22)
        assert v2.timestamp.astimezone(_ISTANBUL_TZ).date() == date(2026, 4, 23)


def test_parse_fleet_defensive_comma_normalization(fleet_at):
    # Upstream has shipped comma-decimals in prior captures (see
    # _research/test_filo_hatkodu_check.py). Parser must normalise.
    synthetic = [
        {
            "Operator": "X", "Garaj": None, "KapiNo": "COMMA-1",
            "Saat": "10:00:00", "Boylam": "29,123", "Enlem": "41,456",
            "Hiz": "12,5", "Plaka": "34 XX 1",
        }
    ]
    envelope = _wrap_envelope(
        "GetFiloAracKonum_json", json.dumps(synthetic, ensure_ascii=False)
    )
    result = _parse_fleet_response(envelope, at=fleet_at)

    assert len(result) == 1
    assert result[0].latitude == pytest.approx(41.456)
    assert result[0].longitude == pytest.approx(29.123)
    assert result[0].speed == pytest.approx(12.5)


def test_parse_fleet_malformed_records_skip(fleet_at, caplog):
    synthetic = [
        {  # ok
            "Operator": "X", "Garaj": None, "KapiNo": "OK-1",
            "Saat": "10:00:00", "Boylam": "29.0", "Enlem": "41.0",
            "Hiz": "0", "Plaka": "34 XX 1",
        },
        {  # invalid_coord
            "Operator": "X", "Garaj": None, "KapiNo": "BADCOORD",
            "Saat": "10:00:00", "Boylam": "abc", "Enlem": "41.0",
            "Hiz": "0", "Plaka": "34 XX 2",
        },
        {  # invalid_time
            "Operator": "X", "Garaj": None, "KapiNo": "BADTIME",
            "Saat": "xyz", "Boylam": "29.0", "Enlem": "41.0",
            "Hiz": "0", "Plaka": "34 XX 3",
        },
        {  # invalid_speed
            "Operator": "X", "Garaj": None, "KapiNo": "BADSPEED",
            "Saat": "10:00:00", "Boylam": "29.0", "Enlem": "41.0",
            "Hiz": "fast", "Plaka": "34 XX 4",
        },
        {  # malformed: missing KapiNo
            "Operator": "X", "Garaj": None,
            "Saat": "10:00:00", "Boylam": "29.0", "Enlem": "41.0",
            "Hiz": "0", "Plaka": "34 XX 5",
        },
    ]
    envelope = _wrap_envelope(
        "GetFiloAracKonum_json", json.dumps(synthetic, ensure_ascii=False)
    )

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        result = _parse_fleet_response(envelope, at=fleet_at)

    assert len(result) == 1
    assert result[0].vehicle_id == "OK-1"
    summary = _extract_summary(caplog, _FLEET_SUMMARY_RE)
    assert summary == {
        "total": 5, "ok": 1, "skipped": 4,
        "invalid_coord": 1, "invalid_speed": 1,
        "invalid_time": 1, "malformed": 1,
    }


def test_parse_fleet_summary_log_shape(filo_fetch_body, fleet_at, caplog):
    # Regression guard on the exact log-line shape. Ops alerts / log
    # queries match on this pattern, so its format is load-bearing.
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        _parse_fleet_response(filo_fetch_body, at=fleet_at)

    summary_records = [
        r for r in caplog.records
        if _FLEET_SUMMARY_RE.search(r.getMessage())
    ]
    assert len(summary_records) == 1
    rec = summary_records[0]
    assert rec.levelno == logging.INFO
    assert rec.name == LOGGER_NAME
    # All seven counter keys must be present in the regex groups.
    groups = _FLEET_SUMMARY_RE.search(rec.getMessage()).groupdict()
    assert set(groups) == {
        "total", "ok", "skipped",
        "invalid_coord", "invalid_speed", "invalid_time", "malformed",
    }
