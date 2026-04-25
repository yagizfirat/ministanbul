"""Tests for ``apps.realtime.enrich.enrich_with_route_id`` — pure helper
that resolves ``route_id`` on a list of ``VehiclePosition`` using the
KapiNo-keyed mapping cache (spec §5.7, ROADMAP 5c, Phase 2 Step 5i-ii
refactor).

Numerical conventions for the 12 inherited tests: ``wall_sec`` numbers
(e.g. 1000, 1500, 2000) are wall-clock seconds since midnight on
``TEST_DATE`` Istanbul-local. Since the helper now uses wall-clock
seconds (5i-ii), the bisect math is identical to the pre-5i-ii epoch-ms
tests once the parameter is interpreted as seconds.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from apps.realtime.calendar import ISTANBUL_TZ
from apps.realtime.enrich import enrich_with_route_id
from apps.realtime.schemas import VehiclePosition

TEST_DATE = date(2026, 4, 22)  # Wednesday → weekday
TEST_DAY_TYPE = "weekday"
_TEST_MIDNIGHT = datetime.combine(TEST_DATE, time.min, tzinfo=ISTANBUL_TZ)


def _make_vehicle(
    vehicle_id: str,
    wall_sec: int,
    *,
    latitude: float = 41.0,
    longitude: float = 29.0,
    source: str = "iett-soap",
    mode: str = "bus",
) -> VehiclePosition:
    """Vehicle with timestamp = TEST_DATE midnight + wall_sec (Istanbul TZ)."""
    return VehiclePosition(
        vehicle_id=vehicle_id,
        latitude=latitude,
        longitude=longitude,
        timestamp=_TEST_MIDNIGHT + timedelta(seconds=wall_sec),
        source=source,
        mode=mode,
    )


def _make_vehicle_local(vehicle_id: str, iso_local: str) -> VehiclePosition:
    """Vehicle with timestamp parsed from a tz-aware ISO 8601 string."""
    return VehiclePosition(
        vehicle_id=vehicle_id,
        latitude=41.0,
        longitude=29.0,
        timestamp=datetime.fromisoformat(iso_local),
        source="iett-soap",
        mode="bus",
    )


def _interval(
    start_sec: int,
    end_sec: int,
    hat: str = "29B",
    guzergah: str | None = None,
) -> dict:
    return {
        "start_sec": start_sec,
        "end_sec": end_sec,
        "hat": hat,
        "guzergah": guzergah or f"{hat}_G_D0",
    }


def _mapping(**by_kapi_kwargs: list[dict]) -> dict:
    """Default mapping: TEST_DATE / TEST_DAY_TYPE metadata, by_kapi from kwargs."""
    return _mapping_with(by_kapi=dict(by_kapi_kwargs))


def _mapping_with(
    *,
    by_kapi: dict | None = None,
    snapshot_date: str | None = None,
    snapshot_day_type: str | None = None,
) -> dict:
    """Mapping with overridable snapshot_date / snapshot_day_type."""
    return {
        "snapshot_date": snapshot_date or TEST_DATE.isoformat(),
        "snapshot_day_type": snapshot_day_type or TEST_DAY_TYPE,
        "by_kapi": by_kapi or {},
        "active_routes": [],
        "routes_by_mode": {"metrobus": [], "bus": []},
    }


def test_exact_match_inside_interval():
    mapping = _mapping(**{"A-231": [_interval(1000, 2000, "29B")]})
    vehicles = [_make_vehicle("A-231", 1500)]
    out = enrich_with_route_id(vehicles, mapping)
    assert out[0].route_id == "29B"


def test_timestamp_equals_start_inclusive():
    mapping = _mapping(**{"A-231": [_interval(1000, 2000, "29B")]})
    vehicles = [_make_vehicle("A-231", 1000)]
    out = enrich_with_route_id(vehicles, mapping)
    assert out[0].route_id == "29B"


def test_timestamp_equals_end_inclusive():
    mapping = _mapping(**{"A-231": [_interval(1000, 2000, "29B")]})
    vehicles = [_make_vehicle("A-231", 2000)]
    out = enrich_with_route_id(vehicles, mapping)
    assert out[0].route_id == "29B"


def test_timestamp_one_sec_after_end_unmapped():
    mapping = _mapping(**{"A-231": [_interval(1000, 2000, "29B")]})
    vehicles = [_make_vehicle("A-231", 2001)]
    out = enrich_with_route_id(vehicles, mapping)
    assert out[0].route_id is None


def test_timestamp_before_first_interval_unmapped():
    mapping = _mapping(**{"A-231": [_interval(1000, 2000, "29B")]})
    vehicles = [_make_vehicle("A-231", 500)]
    out = enrich_with_route_id(vehicles, mapping)
    assert out[0].route_id is None


def test_timestamp_after_last_interval_unmapped():
    mapping = _mapping(**{"A-231": [_interval(1000, 2000, "29B")]})
    vehicles = [_make_vehicle("A-231", 5000)]
    out = enrich_with_route_id(vehicles, mapping)
    assert out[0].route_id is None


def test_kapi_not_in_mapping_unmapped():
    mapping = _mapping(**{"A-231": [_interval(1000, 2000, "29B")]})
    vehicles = [_make_vehicle("X-999", 1500)]
    out = enrich_with_route_id(vehicles, mapping)
    assert out[0].route_id is None


def test_empty_intervals_list_defensive():
    mapping = _mapping(**{"A-231": []})
    vehicles = [_make_vehicle("A-231", 1500)]
    out = enrich_with_route_id(vehicles, mapping)
    assert out[0].route_id is None


def test_overlap_picks_later_start():
    mapping = _mapping(
        **{
            "A-231": [
                _interval(1000, 5000, "29B"),
                _interval(3000, 6000, "15B"),
            ]
        }
    )
    vehicles = [_make_vehicle("A-231", 4000)]
    out = enrich_with_route_id(vehicles, mapping)
    assert out[0].route_id == "15B"


def test_empty_vehicles_list():
    mapping = _mapping(**{"A-231": [_interval(1000, 2000, "29B")]})
    out = enrich_with_route_id([], mapping)
    assert out == []


def test_input_vehicles_not_mutated():
    mapping = _mapping(**{"A-231": [_interval(1000, 2000, "29B")]})
    original = _make_vehicle("A-231", 1500)
    original = original.model_copy(update={"route_id": "PRESET"})
    vehicles = [original]

    out = enrich_with_route_id(vehicles, mapping)

    assert vehicles[0].route_id == "PRESET"
    assert out[0].route_id == "29B"
    assert id(vehicles[0]) != id(out[0])


def test_corrupt_mapping_missing_by_kapi_key():
    mapping = {"active_routes": ["29B"]}  # no by_kapi, no snapshot_date
    vehicles = [
        _make_vehicle("A-231", 1500),
        _make_vehicle("X-999", 1500),
    ]
    out = enrich_with_route_id(vehicles, mapping)
    assert [v.route_id for v in out] == [None, None]


# --- 5i-ii new tests -------------------------------------------------------


def test_overnight_continuation_uses_extended_seconds():
    """snapshot=Friday 2026-04-24 weekday + extended interval [82800, 90000]
    (Fri 23:00 → Sat 01:00). Vehicle ts = Saturday 00:30 IST → next_day_type
    = saturday matches, hour < 4 → overnight bump now_sec = 1800 + 86400 =
    88200, lands inside [82800, 90000] → match."""
    mapping = _mapping_with(
        snapshot_date="2026-04-24",  # Friday
        snapshot_day_type="weekday",
        by_kapi={"A-231": [_interval(82800, 90000, "500T")]},
    )
    vehicles = [_make_vehicle_local("A-231", "2026-04-25T00:30:00+03:00")]
    out = enrich_with_route_id(vehicles, mapping)
    assert out[0].route_id == "500T"


def test_next_day_after_4am_no_overnight_bump():
    """Same mapping as above but vehicle ts = Saturday 05:00 IST → hour >= 4,
    no overnight bump → base_sec = 18000 < start_sec 82800 → no match."""
    mapping = _mapping_with(
        snapshot_date="2026-04-24",
        snapshot_day_type="weekday",
        by_kapi={"A-231": [_interval(82800, 90000, "500T")]},
    )
    vehicles = [_make_vehicle_local("A-231", "2026-04-25T05:00:00+03:00")]
    out = enrich_with_route_id(vehicles, mapping)
    assert out[0].route_id is None


def test_snapshot_date_missing_defensive():
    """No snapshot_date in mapping → overnight check short-circuits to False;
    bisect still works on base_sec."""
    mapping = {
        "by_kapi": {"A-231": [_interval(1000, 2000, "29B")]},
        # no snapshot_date, no snapshot_day_type
    }
    vehicles = [_make_vehicle("A-231", 1500)]
    out = enrich_with_route_id(vehicles, mapping)
    assert out[0].route_id == "29B"


def test_snapshot_day_type_missing_defensive():
    """snapshot_date present, snapshot_day_type absent. Overnight check still
    works (only depends on snapshot_date), bisect proceeds normally."""
    mapping = {
        "snapshot_date": TEST_DATE.isoformat(),
        "by_kapi": {"A-231": [_interval(1000, 2000, "29B")]},
    }
    vehicles = [_make_vehicle("A-231", 1500)]
    out = enrich_with_route_id(vehicles, mapping)
    assert out[0].route_id == "29B"
