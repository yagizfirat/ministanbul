"""Tests for ``apps.realtime.mapping.build_mapping`` — the pure reshaper
that turns a parsed archive record list into the Redis cache payload
documented in spec §5.7.

Phase 2 Step 5i-i refactor: payload is now wall-clock seconds (Istanbul
TZ) per snapshot day, with ``snapshot_date`` + ``snapshot_day_type``
metadata. Overnight tasks extend ``end_sec`` past 86400. Tasks that do
not start on ``snapshot_date`` are skipped.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from apps.realtime.mapping import build_mapping
from apps.realtime.schemas import IettArsivGorev

LOGGER_NAME = "apps.realtime.mapping"
SNAPSHOT_DATE = date(2026, 4, 22)
ISTANBUL_TZ = ZoneInfo("Europe/Istanbul")


def _ts(hour: int, minute: int = 0, second: int = 0, day: int = 22) -> datetime:
    """Istanbul-local timestamp on snapshot date (2026-04-22) by default."""
    return datetime(2026, 4, day, hour, minute, second, tzinfo=ISTANBUL_TZ)


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


def _sec(hour: int, minute: int = 0, second: int = 0) -> int:
    """Wall-clock seconds since midnight."""
    return hour * 3600 + minute * 60 + second


def test_build_empty():
    out = build_mapping([], SNAPSHOT_DATE, "weekday")
    assert out == {
        "snapshot_date": "2026-04-22",
        "snapshot_day_type": "weekday",
        "by_kapi": {},
        "active_routes": [],
        "routes_by_mode": {"metrobus": [], "bus": []},
        # Yol B: empty active_routes short-circuits to an empty PK index
        # (no DB query needed); enrich consumers handle a missing entry
        # as route_id=None.
        "route_id_by_short_name": {},
    }


def test_build_single_task():
    rec = _gorev(
        kapi_no="M2288",
        hat_kodu="15SK",
        guzergah_kodu="15SK_G_D0",
        start_time=_ts(5),
        end_time=_ts(6),
    )
    out = build_mapping([rec], SNAPSHOT_DATE, "weekday")

    assert out["snapshot_date"] == "2026-04-22"
    assert out["snapshot_day_type"] == "weekday"
    assert out["active_routes"] == ["15SK"]
    assert out["routes_by_mode"]["bus"] == ["15SK"]
    assert out["routes_by_mode"]["metrobus"] == []
    assert list(out["by_kapi"]) == ["M2288"]
    (task,) = out["by_kapi"]["M2288"]
    assert task == {
        "start_sec": _sec(5),
        "end_sec": _sec(6),
        "hat": "15SK",
        "guzergah": "15SK_G_D0",
    }


def test_build_multiple_kapi():
    records = [
        _gorev(kapi_no="C-1001", hat_kodu="29B"),
        _gorev(kapi_no="C-1002", hat_kodu="15SK"),
        _gorev(kapi_no="M2072", hat_kodu="34A", guzergah_kodu="34A_G_D0"),
    ]
    out = build_mapping(records, SNAPSHOT_DATE, "weekday")

    assert out["snapshot_day_type"] == "weekday"
    assert set(out["by_kapi"]) == {"C-1001", "C-1002", "M2072"}
    assert out["active_routes"] == ["15SK", "29B", "34A"]
    assert out["routes_by_mode"] == {
        "metrobus": ["34A"],
        "bus": ["15SK", "29B"],
    }


def test_build_interval_sort():
    # Feed three intervals for the same KapiNo in shuffled order; expect
    # ascending start_sec in the output list.
    rec_mid = _gorev(kapi_no="X", hat_kodu="A", start_time=_ts(9), end_time=_ts(10))
    rec_late = _gorev(kapi_no="X", hat_kodu="B", start_time=_ts(13), end_time=_ts(14))
    rec_early = _gorev(kapi_no="X", hat_kodu="C", start_time=_ts(5), end_time=_ts(6))

    out = build_mapping([rec_mid, rec_late, rec_early], SNAPSHOT_DATE, "weekday")

    tasks = out["by_kapi"]["X"]
    assert [t["hat"] for t in tasks] == ["C", "A", "B"]
    assert tasks[0]["start_sec"] < tasks[1]["start_sec"] < tasks[2]["start_sec"]


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
    out = build_mapping(records, SNAPSHOT_DATE, "weekday")

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
    out = build_mapping(records, SNAPSHOT_DATE, "weekday")

    assert list(out["by_kapi"]) == ["C-1001"]
    assert out["active_routes"] == ["29B"]


def test_build_inverted_interval_skipped(caplog):
    """Sentinel: pre-5i-i this used UTC ms; the rename of warn fields to
    ``start_sec``/``end_sec`` is captured in a separate test below."""
    good = _gorev(
        kapi_no="G1", hat_kodu="29B",
        start_time=_ts(5), end_time=_ts(6),
    )
    inverted = _gorev(
        kapi_no="BAD1", hat_kodu="15SK",
        start_time=_ts(8), end_time=_ts(7),  # end < start
    )

    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        out = build_mapping([good, inverted], SNAPSHOT_DATE, "weekday")

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
    out = build_mapping([], date(2026, 4, 22), "weekday")
    assert out["snapshot_date"] == "2026-04-22"
    out2 = build_mapping([], date(2026, 1, 3), "saturday")
    assert out2["snapshot_date"] == "2026-01-03"
    assert out2["snapshot_day_type"] == "saturday"


# --- 5i-i new tests --------------------------------------------------------


def test_build_overnight_interval_extended_seconds():
    """Task starts 23:00 on snapshot day, ends 01:00 next day → end_sec extended."""
    rec = _gorev(
        kapi_no="A-231",
        hat_kodu="500T",
        guzergah_kodu="500T_G_D0",
        start_time=_ts(23, 0, 0, day=22),  # Apr 22 23:00 IST
        end_time=_ts(1, 0, 0, day=23),     # Apr 23 01:00 IST
    )
    out = build_mapping([rec], SNAPSHOT_DATE, "weekday")

    (task,) = out["by_kapi"]["A-231"]
    assert task["start_sec"] == 23 * 3600       # 82800
    assert task["end_sec"] == 86400 + 1 * 3600  # 90000 (extended into next day)
    assert task["hat"] == "500T"


def test_build_skips_task_outside_snapshot_date(caplog):
    """Architectural invariant: only tasks starting on snapshot_date are kept."""
    rec_before = _gorev(
        kapi_no="A-100",
        start_time=_ts(22, 0, 0, day=21),  # day before snapshot (22:00)
        end_time=_ts(6, 0, 0, day=22),     # ends on snapshot morning
    )
    rec_after = _gorev(
        kapi_no="A-200",
        start_time=_ts(8, 0, 0, day=23),   # day after snapshot
        end_time=_ts(10, 0, 0, day=23),
    )
    rec_overshoot = _gorev(
        kapi_no="A-300",
        start_time=_ts(23, 0, 0, day=22),  # starts on snapshot
        end_time=_ts(2, 0, 0, day=24),     # ends two days later — out of scope
    )
    rec_keep = _gorev(
        kapi_no="A-400",
        hat_kodu="29B",
        start_time=_ts(8, 0, 0, day=22),
        end_time=_ts(9, 0, 0, day=22),
    )

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        out = build_mapping(
            [rec_before, rec_after, rec_overshoot, rec_keep],
            SNAPSHOT_DATE, "weekday",
        )

    assert list(out["by_kapi"]) == ["A-400"]
    assert out["active_routes"] == ["29B"]

    # Summary log should account for all 3 skipped tasks under outside_snapshot.
    info_msgs = [r.getMessage() for r in caplog.records if r.levelno == logging.INFO]
    assert any("outside_snapshot=3" in m for m in info_msgs)


def test_build_skips_inverted_same_day_in_seconds(caplog):
    """End_sec < start_sec on the same day → still inverted, still skipped.

    Distinct from ``test_build_inverted_interval_skipped`` which preceded
    the wall-clock refactor: this guards the new ``end_sec``-based check.
    """
    inverted = _gorev(
        kapi_no="BAD2", hat_kodu="36T",
        start_time=_ts(23, 30, 0),  # 23:30
        end_time=_ts(22, 0, 0),     # 22:00 same day → end_sec < start_sec
    )

    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        out = build_mapping([inverted], SNAPSHOT_DATE, "weekday")

    assert out["by_kapi"] == {}
    assert out["active_routes"] == []

    warn_msgs = [
        r.getMessage() for r in caplog.records
        if r.levelno == logging.WARNING and "inverted interval" in r.getMessage()
    ]
    assert len(warn_msgs) == 1
    assert "kapi=BAD2" in warn_msgs[0]
    assert "start_sec=" in warn_msgs[0]  # field renamed from start_ms
    assert "end_sec=" in warn_msgs[0]
