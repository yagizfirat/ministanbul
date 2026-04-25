"""Tests for ``apps.realtime.enrich.enrich_with_route_id`` — pure helper
that resolves ``route_id`` on a list of ``VehiclePosition`` using the
KapiNo-keyed mapping cache (spec §5.7, ROADMAP 5c).
"""
from __future__ import annotations

from datetime import datetime, timezone

from apps.realtime.enrich import enrich_with_route_id
from apps.realtime.schemas import VehiclePosition


def _dt_from_ms(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def _make_vehicle(
    vehicle_id: str,
    ts_ms: int,
    *,
    latitude: float = 41.0,
    longitude: float = 29.0,
    source: str = "iett-soap",
    mode: str = "bus",
) -> VehiclePosition:
    return VehiclePosition(
        vehicle_id=vehicle_id,
        latitude=latitude,
        longitude=longitude,
        timestamp=_dt_from_ms(ts_ms),
        source=source,
        mode=mode,
    )


def _interval(
    start_ms: int,
    end_ms: int,
    hat: str = "29B",
    guzergah: str | None = None,
) -> dict:
    return {
        "start_ms": start_ms,
        "end_ms": end_ms,
        "hat": hat,
        "guzergah": guzergah or f"{hat}_G_D0",
    }


def _mapping(**by_kapi_kwargs: list[dict]) -> dict:
    return {
        "by_kapi": dict(by_kapi_kwargs),
        "active_routes": [],
        "routes_by_mode": {"metrobus": [], "bus": []},
    }


def test_exact_match_inside_interval():
    mapping = _mapping(**{"A-231": [_interval(1000, 2000, "29B")]})
    vehicles = [_make_vehicle("A-231", 1500)]
    out = enrich_with_route_id(vehicles, mapping)
    assert out[0].route_id == "29B"


def test_timestamp_equals_start_ms_inclusive():
    mapping = _mapping(**{"A-231": [_interval(1000, 2000, "29B")]})
    vehicles = [_make_vehicle("A-231", 1000)]
    out = enrich_with_route_id(vehicles, mapping)
    assert out[0].route_id == "29B"


def test_timestamp_equals_end_ms_inclusive():
    mapping = _mapping(**{"A-231": [_interval(1000, 2000, "29B")]})
    vehicles = [_make_vehicle("A-231", 2000)]
    out = enrich_with_route_id(vehicles, mapping)
    assert out[0].route_id == "29B"


def test_timestamp_one_ms_after_end_unmapped():
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
    mapping = {"active_routes": ["29B"]}
    vehicles = [
        _make_vehicle("A-231", 1500),
        _make_vehicle("X-999", 1500),
    ]
    out = enrich_with_route_id(vehicles, mapping)
    assert [v.route_id for v in out] == [None, None]
