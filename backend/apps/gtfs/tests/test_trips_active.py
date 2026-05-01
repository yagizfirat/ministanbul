"""Tests for /api/trips/active/ endpoint (Faz 5 KM2)."""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from django.contrib.gis.geos import Point
from django.urls import reverse
from rest_framework.test import APIClient

from apps.gtfs.models import (
    Agency, Calendar, Route, Stop, StopTime, Trip,
)
from apps.gtfs.timeutils import ISTANBUL


# 2026-05-02 is a Saturday; 2026-05-08 Friday avoids the 2026-05-01 Friday
# (İşçi Bayramı) — but the endpoint reads only Calendar.<weekday> flags,
# Turkish holidays are not part of the v0 contract. Pick a clean Friday.
FRIDAY_AT_1415 = datetime(2026, 5, 8, 14, 15, 0, tzinfo=ISTANBUL)


@pytest.fixture
def base_data(db):
    """Build a small fixture set: 2 calendars, 4 routes, 4 trips, stop_times.

    Times encode the test scenarios:
      - WEEKDAY service active on Friday; WEEKEND only Sat/Sun.
      - "in_window" trips: 14:00 -> 14:30 (covers 14:15).
      - "out_window" trip: 13:00 -> 13:10 (already finished by 14:15).
    """
    Calendar.objects.create(
        service_id="WEEKDAY",
        monday=True, tuesday=True, wednesday=True, thursday=True, friday=True,
        saturday=False, sunday=False,
        start_date=date(2020, 1, 1), end_date=date(2099, 12, 31),
    )
    Calendar.objects.create(
        service_id="WEEKEND",
        monday=False, tuesday=False, wednesday=False, thursday=False, friday=False,
        saturday=True, sunday=True,
        start_date=date(2020, 1, 1), end_date=date(2099, 12, 31),
    )

    agency = Agency.objects.create(
        agency_id="ag1", name="Test", url="http://x", timezone="Europe/Istanbul",
    )

    route_metro = Route.objects.create(
        route_id="public:m2", agency=agency,
        short_name="M2", long_name="YENIKAPI - HACIOSMAN", route_type=1,
    )
    route_marmaray = Route.objects.create(
        route_id="public:marmaray", agency=agency,
        short_name="Marmaray", long_name="GEBZE - HALKALI", route_type=1,
    )
    route_ferry = Route.objects.create(
        route_id="public:f1", agency=agency,
        short_name="F1", long_name="KADIKOY - KARAKOY", route_type=4,
    )
    # Bus from iETT feed — must NOT leak into any mode response.
    route_bus = Route.objects.create(
        route_id="iett:34", agency=agency,
        short_name="34", long_name="METROBUS", route_type=3,
    )

    s1 = Stop.objects.create(stop_id="s1", name="A", location=Point(29.0, 41.0))
    s2 = Stop.objects.create(stop_id="s2", name="B", location=Point(29.01, 41.01))
    s3 = Stop.objects.create(stop_id="s3", name="C", location=Point(29.02, 41.02))

    def _add_stop_times(trip: Trip, start: timedelta, end: timedelta) -> None:
        mid = start + (end - start) / 2
        StopTime.objects.create(trip=trip, stop=s1, arrival_time=start,
                                departure_time=start, stop_sequence=1)
        StopTime.objects.create(trip=trip, stop=s2, arrival_time=mid,
                                departure_time=mid, stop_sequence=2)
        StopTime.objects.create(trip=trip, stop=s3, arrival_time=end,
                                departure_time=end, stop_sequence=3)

    metro_in = Trip.objects.create(
        trip_id="metro_in", route=route_metro, headsign="HACIOSMAN",
        direction_id=0, service_id="WEEKDAY",
    )
    _add_stop_times(metro_in, timedelta(hours=14), timedelta(hours=14, minutes=30))

    metro_out = Trip.objects.create(
        trip_id="metro_out", route=route_metro, headsign="HACIOSMAN",
        direction_id=0, service_id="WEEKDAY",
    )
    _add_stop_times(metro_out, timedelta(hours=13), timedelta(hours=13, minutes=10))

    marmaray_in = Trip.objects.create(
        trip_id="marmaray_in", route=route_marmaray, headsign="HALKALI",
        direction_id=0, service_id="WEEKDAY",
    )
    _add_stop_times(marmaray_in, timedelta(hours=14), timedelta(hours=14, minutes=30))

    ferry_weekend = Trip.objects.create(
        trip_id="ferry_weekend", route=route_ferry, headsign="KARAKOY",
        direction_id=0, service_id="WEEKEND",
    )
    _add_stop_times(ferry_weekend, timedelta(hours=14), timedelta(hours=14, minutes=30))

    # iETT bus during the same window — must be excluded.
    bus_in = Trip.objects.create(
        trip_id="bus_in", route=route_bus, headsign="AVCILAR",
        direction_id=0, service_id="WEEKDAY",
    )
    _add_stop_times(bus_in, timedelta(hours=14), timedelta(hours=14, minutes=30))

    return {
        "metro_in": metro_in, "metro_out": metro_out,
        "marmaray_in": marmaray_in, "ferry_weekend": ferry_weekend,
        "bus_in": bus_in,
    }


@pytest.fixture
def client_fri(monkeypatch):
    """APIClient with now_istanbul mocked to a clean Friday 14:15 Istanbul."""
    monkeypatch.setattr(
        "apps.gtfs.views.now_istanbul", lambda: FRIDAY_AT_1415,
    )
    return APIClient()


URL = "/api/trips/active/"


# --- validation -----------------------------------------------------------


def test_mode_required(client_fri, base_data):
    r = client_fri.get(URL)
    assert r.status_code == 400


def test_mode_invalid(client_fri, base_data):
    r = client_fri.get(URL, {"mode": "spaceship"})
    assert r.status_code == 400


def test_time_invalid(client_fri, base_data):
    r = client_fri.get(URL, {"mode": "metro", "time": "foo"})
    assert r.status_code == 400


def test_time_format_parses(client_fri, base_data):
    r = client_fri.get(URL, {"mode": "metro", "time": "14:15:00"})
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "metro"
    assert body["count"] == 1
    assert body["trips"][0]["trip_id"] == "metro_in"


# --- mode filtering -------------------------------------------------------


def test_metro_returns_metro_trips_only(client_fri, base_data):
    r = client_fri.get(URL, {"mode": "metro"})
    assert r.status_code == 200
    trip_ids = {t["trip_id"] for t in r.json()["trips"]}
    assert trip_ids == {"metro_in"}  # excludes Marmaray, ferry, bus, out-window


def test_marmaray_excluded_from_metro(client_fri, base_data):
    r = client_fri.get(URL, {"mode": "metro"})
    trip_ids = {t["trip_id"] for t in r.json()["trips"]}
    assert "marmaray_in" not in trip_ids


def test_marmaray_returns_marmaray(client_fri, base_data):
    r = client_fri.get(URL, {"mode": "marmaray"})
    trip_ids = {t["trip_id"] for t in r.json()["trips"]}
    assert trip_ids == {"marmaray_in"}


def test_bus_never_included_in_any_mode(client_fri, base_data):
    """iETT route_id='iett:34' bus must not leak — public-prefix filter."""
    for mode in ("metro", "marmaray", "tram", "funicular", "ferry"):
        r = client_fri.get(URL, {"mode": mode})
        trip_ids = {t["trip_id"] for t in r.json()["trips"]}
        assert "bus_in" not in trip_ids, f"bus leaked into mode={mode}"


# --- temporal -------------------------------------------------------------


def test_window_filter_excludes_finished_trips(client_fri, base_data):
    r = client_fri.get(URL, {"mode": "metro", "time": "14:15:00"})
    trip_ids = {t["trip_id"] for t in r.json()["trips"]}
    assert "metro_out" not in trip_ids


def test_weekday_filter_excludes_weekend_service(client_fri, base_data):
    """Friday request should NOT see the WEEKEND-service ferry."""
    r = client_fri.get(URL, {"mode": "ferry"})
    assert r.json()["count"] == 0


# --- response shape -------------------------------------------------------


def test_response_shape_has_required_fields(client_fri, base_data):
    r = client_fri.get(URL, {"mode": "metro"})
    trip = r.json()["trips"][0]
    for key in ("trip_id", "route_id", "route_short_name", "route_long_name",
                "shape_id", "direction_id", "headsign", "mode", "stop_times"):
        assert key in trip, f"missing key: {key}"
    assert trip["mode"] == "metro"


def test_stop_times_sorted_by_sequence(client_fri, base_data):
    r = client_fri.get(URL, {"mode": "metro"})
    sts = r.json()["trips"][0]["stop_times"]
    seqs = [st["sequence"] for st in sts]
    assert seqs == sorted(seqs)
    assert seqs == [1, 2, 3]


def test_arrival_time_serialized_as_int_seconds(client_fri, base_data):
    r = client_fri.get(URL, {"mode": "metro"})
    sts = r.json()["trips"][0]["stop_times"]
    arrivals = [st["arrival_seconds"] for st in sts]
    # 14:00 -> 14:15 -> 14:30 = 50400, 51300, 52200
    assert arrivals == [50400, 51300, 52200]
    for a in arrivals:
        assert isinstance(a, int)


def test_cache_control_header(client_fri, base_data):
    r = client_fri.get(URL, {"mode": "metro"})
    cc = r.headers.get("Cache-Control", "")
    assert "max-age=60" in cc
    assert "public" in cc
