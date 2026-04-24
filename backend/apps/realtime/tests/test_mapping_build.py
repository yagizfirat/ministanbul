"""Tests for ``apps.realtime.mapping.build_mapping`` — the pure reshaper
that turns a parsed archive record list into the Redis cache payload
documented in spec §5.7.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone

import pytest

from apps.realtime.mapping import build_mapping
from apps.realtime.schemas import IettArsivGorev

LOGGER_NAME = "apps.realtime.mapping"
SNAPSHOT_DATE = date(2026, 4, 22)


def _ts(hour: int, minute: int = 0, second: int = 0) -> datetime:
    return datetime(2026, 4, 22, hour, minute, second, tzinfo=timezone.utc)


def _gorev(
    *,
    kapi_no: str = "M2288",
    hat_kodu: str = "15SK",
    guzergah_kodu: str = "15SK_G_D0",
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    gorev_durum: str = "T",
) -> IettArsivGorev:
    return IettArsivGorev(
        kapi_no=kapi_no,
        hat_kodu=hat_kodu,
        guzergah_kodu=guzergah_kodu,
        start_time=start_time or _ts(5),
        end_time=end_time or _ts(6),
        gorev_durum=gorev_durum,
    )


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def test_build_empty():
    out = build_mapping([], SNAPSHOT_DATE)
    assert out == {
        "date": "2026-04-22",
        "by_kapi": {},
        "active_routes": [],
        "routes_by_mode": {"metrobus": [], "bus": []},
    }


def test_build_single_task():
    rec = _gorev(
        kapi_no="M2288",
        hat_kodu="15SK",
        guzergah_kodu="15SK_G_D0",
        start_time=_ts(5),
        end_time=_ts(6),
    )
    out = build_mapping([rec], SNAPSHOT_DATE)

    assert out["date"] == "2026-04-22"
    assert out["active_routes"] == ["15SK"]
    assert out["routes_by_mode"]["bus"] == ["15SK"]
    assert out["routes_by_mode"]["metrobus"] == []
    assert list(out["by_kapi"]) == ["M2288"]
    (task,) = out["by_kapi"]["M2288"]
    assert task == {
        "start_ms": _ms(_ts(5)),
        "end_ms": _ms(_ts(6)),
        "hat": "15SK",
        "guzergah": "15SK_G_D0",
    }


def test_build_multiple_kapi():
    records = [
        _gorev(kapi_no="C-1001", hat_kodu="29B"),
        _gorev(kapi_no="C-1002", hat_kodu="15SK"),
        _gorev(kapi_no="M2072", hat_kodu="34A", guzergah_kodu="34A_G_D0"),
    ]
    out = build_mapping(records, SNAPSHOT_DATE)

    assert set(out["by_kapi"]) == {"C-1001", "C-1002", "M2072"}
    assert out["active_routes"] == ["15SK", "29B", "34A"]
    assert out["routes_by_mode"] == {
        "metrobus": ["34A"],
        "bus": ["15SK", "29B"],
    }


def test_build_interval_sort():
    # Feed three intervals for the same KapiNo in shuffled order; expect
    # ascending start_ms in the output list.
    rec_mid = _gorev(kapi_no="X", hat_kodu="A", start_time=_ts(9), end_time=_ts(10))
    rec_late = _gorev(kapi_no="X", hat_kodu="B", start_time=_ts(13), end_time=_ts(14))
    rec_early = _gorev(kapi_no="X", hat_kodu="C", start_time=_ts(5), end_time=_ts(6))

    out = build_mapping([rec_mid, rec_late, rec_early], SNAPSHOT_DATE)

    tasks = out["by_kapi"]["X"]
    assert [t["hat"] for t in tasks] == ["C", "A", "B"]
    assert tasks[0]["start_ms"] < tasks[1]["start_ms"] < tasks[2]["start_ms"]


def test_build_metrobus_classification():
    records = [
        _gorev(kapi_no="MB1", hat_kodu="34"),
        _gorev(kapi_no="MB2", hat_kodu="34A"),
        _gorev(kapi_no="MB3", hat_kodu="34BZ"),
        _gorev(kapi_no="B1", hat_kodu="15SK"),
        _gorev(kapi_no="B2", hat_kodu="29B"),
        _gorev(kapi_no="B3", hat_kodu="500T"),
        _gorev(kapi_no="B4", hat_kodu="HA-3"),
        _gorev(kapi_no="B5", hat_kodu="M2288X"),
    ]
    out = build_mapping(records, SNAPSHOT_DATE)

    assert out["routes_by_mode"]["metrobus"] == ["34", "34A", "34BZ"]
    assert out["routes_by_mode"]["bus"] == ["15SK", "29B", "500T", "HA-3", "M2288X"]
    # Invariants: the two sets partition active_routes.
    assert (
        set(out["routes_by_mode"]["metrobus"])
        | set(out["routes_by_mode"]["bus"])
        == set(out["active_routes"])
    )
    assert (
        set(out["routes_by_mode"]["metrobus"])
        & set(out["routes_by_mode"]["bus"])
        == set()
    )


def test_build_null_kapino_skipped():
    records = [
        _gorev(kapi_no="", hat_kodu="29B"),        # empty string: skip
        _gorev(kapi_no="C-1001", hat_kodu="29B"),  # keep
    ]
    out = build_mapping(records, SNAPSHOT_DATE)

    assert list(out["by_kapi"]) == ["C-1001"]
    assert out["active_routes"] == ["29B"]


def test_build_inverted_interval_skipped(caplog):
    good = _gorev(
        kapi_no="G1", hat_kodu="29B",
        start_time=_ts(5), end_time=_ts(6),
    )
    inverted = _gorev(
        kapi_no="BAD1", hat_kodu="15SK",
        start_time=_ts(8), end_time=_ts(7),  # end < start
    )

    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        out = build_mapping([good, inverted], SNAPSHOT_DATE)

    assert list(out["by_kapi"]) == ["G1"]
    assert out["active_routes"] == ["29B"]

    warn_msgs = [
        r.getMessage() for r in caplog.records
        if r.levelno == logging.WARNING and "inverted interval" in r.getMessage()
    ]
    assert len(warn_msgs) == 1
    assert "kapi=BAD1" in warn_msgs[0]
    assert "hat=15SK" in warn_msgs[0]


def test_build_uses_isoformat():
    out = build_mapping([], date(2026, 4, 22))
    assert out["date"] == "2026-04-22"
    out2 = build_mapping([], date(2026, 1, 3))
    assert out2["date"] == "2026-01-03"
