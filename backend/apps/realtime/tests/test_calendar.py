"""Tests for ``apps.realtime.calendar`` — day-type helpers + holiday-aware
target-date selection (Phase 2 Step 5i-iii).

Reference dates picked so each branch hits a real Turkish holiday:

  - 2026-04-22 Wed: normal weekday
  - 2026-04-23 Thu: Ulusal Egemenlik ve Çocuk Bayramı (HOLIDAY)
  - 2026-04-25 Sat: normal Saturday
  - 2026-04-26 Sun: normal Sunday
  - 2026-04-30 Thu: normal weekday whose 7-day-back (2026-04-23) is a HOLIDAY
                    → exercises the 14-day fallback
  - 2026-05-01 Fri: İşçi Bayramı (HOLIDAY)
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

import pytest

from apps.realtime import calendar as calendar_mod
from apps.realtime.calendar import (
    TURKEY_HOLIDAYS,
    _last_sunday_before,
    get_day_type,
    pick_target_date,
)

LOGGER_NAME = "apps.realtime.calendar"


# --- get_day_type matrix -------------------------------------------------


def test_get_day_type_normal_weekday():
    # 2026-04-22 Çarşamba, no holiday
    assert get_day_type(date(2026, 4, 22)) == "weekday"


def test_get_day_type_normal_saturday():
    assert get_day_type(date(2026, 4, 25)) == "saturday"


def test_get_day_type_normal_sunday():
    assert get_day_type(date(2026, 4, 26)) == "sunday"


def test_get_day_type_holiday_returns_sunday():
    # 2026-04-23 Perşembe — Ulusal Egemenlik Bayramı, holiday
    assert date(2026, 4, 23) in TURKEY_HOLIDAYS  # sanity
    assert get_day_type(date(2026, 4, 23)) == "sunday"


def test_get_day_type_friday_holiday_also_sunday():
    # 2026-05-01 Cuma — İşçi Bayramı
    assert date(2026, 5, 1) in TURKEY_HOLIDAYS  # sanity
    assert get_day_type(date(2026, 5, 1)) == "sunday"


# --- _last_sunday_before -------------------------------------------------


def test_last_sunday_before_weekday():
    # Wed 2026-04-22 → previous Sun = 2026-04-19
    assert _last_sunday_before(date(2026, 4, 22)) == date(2026, 4, 19)


def test_last_sunday_before_sunday_returns_previous():
    # Sun 2026-04-26 → previous Sun = 2026-04-19 (one week earlier)
    assert _last_sunday_before(date(2026, 4, 26)) == date(2026, 4, 19)


# --- pick_target_date ----------------------------------------------------


def test_pick_target_date_normal_weekday():
    # today=2026-04-22 Wed normal → 7 days back = 2026-04-15 Wed normal
    target, dt = pick_target_date(date(2026, 4, 22))
    assert target == date(2026, 4, 15)
    assert dt == "weekday"


def test_pick_target_date_normal_saturday():
    # today=2026-04-25 Sat normal → 7 days back = 2026-04-18 Sat normal
    target, dt = pick_target_date(date(2026, 4, 25))
    assert target == date(2026, 4, 18)
    assert dt == "saturday"


def test_pick_target_date_today_is_holiday_uses_last_sunday():
    # today=2026-04-23 Thu HOLIDAY → last Sunday = 2026-04-19
    target, dt = pick_target_date(date(2026, 4, 23))
    assert target == date(2026, 4, 19)
    assert dt == "sunday"


def test_pick_target_date_7_day_back_is_holiday_uses_14_day():
    # today=2026-04-30 Thu normal, 7-day-back = 2026-04-23 HOLIDAY,
    # 14-day-back = 2026-04-16 Thu normal → target = 2026-04-16
    target, dt = pick_target_date(date(2026, 4, 30))
    assert target == date(2026, 4, 16)
    assert dt == "weekday"


def test_pick_target_date_14_day_back_also_holiday_alarm_and_sunday(
    monkeypatch, caplog,
):
    """Synthetic: monkeypatch TURKEY_HOLIDAYS to mark today-7 AND today-14
    as holidays. Real Turkish calendar rarely chains holidays this way;
    this guards the alarm-log + last-Sunday fallback branch."""
    today = date(2026, 4, 30)
    fake_holidays = {today - timedelta(days=7), today - timedelta(days=14)}
    # Patch the module-level TURKEY_HOLIDAYS used inside pick_target_date.
    monkeypatch.setattr(calendar_mod, "TURKEY_HOLIDAYS", fake_holidays)

    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        target, dt = pick_target_date(today)

    # today (2026-04-30) NOT in fake_holidays → won't take the
    # "today is holiday" branch; falls through to 7→14→sunday chain.
    assert target == _last_sunday_before(today)  # = 2026-04-26 Sunday
    assert dt == "sunday"

    alarm_msgs = [
        r.getMessage() for r in caplog.records
        if r.levelno == logging.WARNING
        and "both 7-day and 14-day fallback are holidays" in r.getMessage()
    ]
    assert len(alarm_msgs) == 1


def test_pick_target_date_day_type_describes_target_not_today():
    """Invariant: ``snapshot_day_type`` always describes ``target_date``,
    never ``today``. Holiday substitution explicitly returns "sunday"."""
    # today=2026-05-01 Fri HOLIDAY → target = last Sunday (2026-04-26),
    # day_type = "sunday" (matches target, not today's "weekday" by raw
    # weekday).
    target, dt = pick_target_date(date(2026, 5, 1))
    assert target == date(2026, 4, 26)
    assert dt == "sunday"
    # And by construction get_day_type(target) == dt
    assert get_day_type(target) == dt
