from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from apps.realtime.schemas import IettArsivGorev, VehiclePosition, parse_msdate


def _dt(year=2026, month=4, day=22, hour=12, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def test_vehicleposition_valid():
    vp = VehiclePosition(
        vehicle_id="M2288",
        route_id="15SK",
        trip_id="15SK_G_D0",
        latitude=41.0082,
        longitude=28.9784,
        bearing=90.0,
        speed=25.5,
        timestamp=_dt(),
        source="iett-soap",
        mode="bus",
    )
    assert vp.vehicle_id == "M2288"
    assert vp.route_id == "15SK"
    assert vp.bearing == 90.0


def test_vehicleposition_optional_fields_none():
    vp = VehiclePosition(
        vehicle_id="M2288",
        latitude=41.0,
        longitude=29.0,
        timestamp=_dt(),
        source="iett-soap",
        mode="bus",
    )
    assert vp.route_id is None
    assert vp.trip_id is None
    assert vp.bearing is None
    assert vp.speed is None


def test_vehicleposition_missing_required_raises():
    with pytest.raises(ValidationError):
        VehiclePosition(
            vehicle_id="M2288",
            # latitude intentionally missing
            longitude=29.0,
            timestamp=_dt(),
            source="iett-soap",
            mode="bus",
        )


def test_iettarsivgorev_valid():
    g = IettArsivGorev(
        kapi_no="M2288",
        hat_kodu="15SK",
        guzergah_kodu="15SK_G_D0",
        start_time=_dt(hour=5),
        end_time=_dt(hour=6),
        gorev_durum="T",
    )
    assert g.kapi_no == "M2288"
    assert g.guzergah_kodu == "15SK_G_D0"
    assert g.gorev_durum == "T"


def test_parse_msdate_basic():
    dt = parse_msdate("/Date(1776863726000)/")
    assert dt.tzinfo is not None
    assert dt.utcoffset() == timedelta(0)
    assert dt == datetime.fromtimestamp(1776863726, tz=timezone.utc)


def test_parse_msdate_with_timezone():
    dt = parse_msdate("/Date(1776863726000+0300)/")
    assert dt.tzinfo is not None
    assert dt.utcoffset() == timedelta(hours=3)
    # Same absolute instant as the UTC variant.
    assert dt.timestamp() == 1776863726.0


def test_parse_msdate_invalid_raises():
    with pytest.raises(ValueError):
        parse_msdate("/Date(xyz)/")
