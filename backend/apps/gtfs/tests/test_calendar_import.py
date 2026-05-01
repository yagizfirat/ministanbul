"""Tests for Calendar model + import_gtfs._load_calendar (Faz 5 KM1).

calendar_dates.txt is intentionally not imported (deferred to Faz 6
polish); these tests only cover calendar.txt.
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from apps.gtfs.management.commands.import_gtfs import (
    Command,
    _parse_gtfs_bool,
    _parse_gtfs_date,
)
from apps.gtfs.models import Calendar


def _make_df(rows: list[dict]) -> pd.DataFrame:
    """DataFrame mirroring import_gtfs's pandas.read_csv settings (dtype=str)."""
    return pd.DataFrame(rows).astype(str)


@pytest.fixture
def fixture_rows() -> list[dict]:
    return [
        {
            "service_id": "WEEKDAYS",
            "monday": "1", "tuesday": "1", "wednesday": "1",
            "thursday": "1", "friday": "1", "saturday": "0", "sunday": "0",
            "start_date": "20260101", "end_date": "20261231",
        },
        {
            "service_id": "WEEKEND",
            "monday": "0", "tuesday": "0", "wednesday": "0",
            "thursday": "0", "friday": "0", "saturday": "1", "sunday": "1",
            "start_date": "20260101", "end_date": "20261231",
        },
        {
            "service_id": "FRIDAY_ONLY",
            "monday": "0", "tuesday": "0", "wednesday": "0",
            "thursday": "0", "friday": "1", "saturday": "0", "sunday": "0",
            "start_date": "20260301", "end_date": "20260601",
        },
    ]


# --- helpers ---------------------------------------------------------------


def test_parse_gtfs_date_valid():
    assert _parse_gtfs_date("20240315") == date(2024, 3, 15)


def test_parse_gtfs_date_invalid_returns_none():
    assert _parse_gtfs_date("") is None
    assert _parse_gtfs_date("notadate") is None
    assert _parse_gtfs_date(None) is None


def test_parse_gtfs_bool():
    assert _parse_gtfs_bool("1") is True
    assert _parse_gtfs_bool("0") is False
    assert _parse_gtfs_bool("") is False
    assert _parse_gtfs_bool(None) is False


# --- import behaviour ------------------------------------------------------


@pytest.mark.django_db
def test_import_calendar_inserts_rows_with_correct_fields(fixture_rows):
    df = _make_df(fixture_rows)
    inserted = Command()._load_calendar(df, label="test")
    assert inserted == 3
    assert Calendar.objects.count() == 3

    weekdays = Calendar.objects.get(service_id="WEEKDAYS")
    assert weekdays.monday is True
    assert weekdays.friday is True
    assert weekdays.saturday is False
    assert weekdays.sunday is False
    assert weekdays.start_date == date(2026, 1, 1)
    assert weekdays.end_date == date(2026, 12, 31)

    weekend = Calendar.objects.get(service_id="WEEKEND")
    assert weekend.saturday is True
    assert weekend.sunday is True
    assert weekend.monday is False

    friday_only = Calendar.objects.get(service_id="FRIDAY_ONLY")
    assert friday_only.friday is True
    assert friday_only.start_date == date(2026, 3, 1)


@pytest.mark.django_db
def test_import_skips_rows_with_blank_service_id_or_bad_date(fixture_rows):
    rows = fixture_rows + [
        {"service_id": "", "monday": "1", "tuesday": "0", "wednesday": "0",
         "thursday": "0", "friday": "0", "saturday": "0", "sunday": "0",
         "start_date": "20260101", "end_date": "20261231"},
        {"service_id": "BAD_DATE", "monday": "1", "tuesday": "0",
         "wednesday": "0", "thursday": "0", "friday": "0",
         "saturday": "0", "sunday": "0",
         "start_date": "garbage", "end_date": "20261231"},
    ]
    df = _make_df(rows)
    inserted = Command()._load_calendar(df, label="test")
    assert inserted == 3
    assert not Calendar.objects.filter(service_id="").exists()
    assert not Calendar.objects.filter(service_id="BAD_DATE").exists()


@pytest.mark.django_db
def test_friday_filter_matches_expected_services(fixture_rows):
    df = _make_df(fixture_rows)
    Command()._load_calendar(df, label="test")
    friday_services = set(
        Calendar.objects.filter(friday=True).values_list("service_id", flat=True)
    )
    assert friday_services == {"WEEKDAYS", "FRIDAY_ONLY"}


@pytest.mark.django_db
def test_empty_dataframe_returns_zero():
    df = pd.DataFrame()
    inserted = Command()._load_calendar(df, label="test")
    assert inserted == 0
    assert Calendar.objects.count() == 0
