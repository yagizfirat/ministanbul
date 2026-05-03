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

import pytest

from apps.realtime.calendar import ISTANBUL_TZ
from apps.realtime.enrich import enrich_with_route_id
from apps.realtime.schemas import VehiclePosition
from apps.realtime.tests._helpers import EXPECTED_PK_FOR_HAT

TEST_DATE = date(2026, 4, 22)  # Wednesday → weekday
TEST_DAY_TYPE = "weekday"
_TEST_MIDNIGHT = datetime.combine(TEST_DATE, time.min, tzinfo=ISTANBUL_TZ)


# KM5-a: ``IETT_BUS_MAPPING_ENABLED`` settings flag default v0.8.0'da
# False (Spec §5.7, Ek A.18 R12). Bu modüldeki testler hibernation
# davranışını (flag açıkken eski mapping path) kontrol ediyor —
# tümünün doğru çalışabilmesi için autouse fixture flag'ı True yapar.
# Flag=False tarafının davranışı dosyanın sonundaki yeni testlerde
# açıkça override ile test edilir.
@pytest.fixture(autouse=True)
def _enable_iett_bus_mapping(settings):
    settings.IETT_BUS_MAPPING_ENABLED = True


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
    route_id_by_short_name: dict | None = None,
) -> dict:
    """Mapping with overridable snapshot_date / snapshot_day_type.

    Yol B: ``route_id_by_short_name`` is auto-derived from the SHATKODU
    values in ``by_kapi`` using ``EXPECTED_PK_FOR_HAT``. Tests assert
    against PK literals (``"iett:1562"``) rather than short_names.
    Defensive tests can pass ``route_id_by_short_name={}`` explicitly to
    simulate an old-format snapshot.
    """
    by_kapi = by_kapi or {}
    if route_id_by_short_name is None:
        active = {iv["hat"] for ivs in by_kapi.values() for iv in ivs}
        route_id_by_short_name = {
            sn: EXPECTED_PK_FOR_HAT[sn]
            for sn in active
            if sn in EXPECTED_PK_FOR_HAT
        }
    return {
        "snapshot_date": snapshot_date or TEST_DATE.isoformat(),
        "snapshot_day_type": snapshot_day_type or TEST_DAY_TYPE,
        "by_kapi": by_kapi,
        "active_routes": [],
        "routes_by_mode": {"metrobus": [], "bus": []},
        "route_id_by_short_name": route_id_by_short_name,
    }


def test_exact_match_inside_interval():
    mapping = _mapping(**{"A-231": [_interval(1000, 2000, "29B")]})
    vehicles = [_make_vehicle("A-231", 1500)]
    out, _ = enrich_with_route_id(vehicles, mapping)
    assert out[0].route_id == EXPECTED_PK_FOR_HAT["29B"]


def test_timestamp_equals_start_inclusive():
    mapping = _mapping(**{"A-231": [_interval(1000, 2000, "29B")]})
    vehicles = [_make_vehicle("A-231", 1000)]
    out, _ = enrich_with_route_id(vehicles, mapping)
    assert out[0].route_id == EXPECTED_PK_FOR_HAT["29B"]


def test_timestamp_equals_end_inclusive():
    mapping = _mapping(**{"A-231": [_interval(1000, 2000, "29B")]})
    vehicles = [_make_vehicle("A-231", 2000)]
    out, _ = enrich_with_route_id(vehicles, mapping)
    assert out[0].route_id == EXPECTED_PK_FOR_HAT["29B"]


def test_timestamp_one_sec_after_end_unmapped():
    mapping = _mapping(**{"A-231": [_interval(1000, 2000, "29B")]})
    vehicles = [_make_vehicle("A-231", 2001)]
    out, _ = enrich_with_route_id(vehicles, mapping)
    assert out[0].route_id is None


def test_timestamp_before_first_interval_unmapped():
    mapping = _mapping(**{"A-231": [_interval(1000, 2000, "29B")]})
    vehicles = [_make_vehicle("A-231", 500)]
    out, _ = enrich_with_route_id(vehicles, mapping)
    assert out[0].route_id is None


def test_timestamp_after_last_interval_unmapped():
    mapping = _mapping(**{"A-231": [_interval(1000, 2000, "29B")]})
    vehicles = [_make_vehicle("A-231", 5000)]
    out, _ = enrich_with_route_id(vehicles, mapping)
    assert out[0].route_id is None


def test_kapi_not_in_mapping_unmapped():
    mapping = _mapping(**{"A-231": [_interval(1000, 2000, "29B")]})
    vehicles = [_make_vehicle("X-999", 1500)]
    out, _ = enrich_with_route_id(vehicles, mapping)
    assert out[0].route_id is None


def test_empty_intervals_list_defensive():
    mapping = _mapping(**{"A-231": []})
    vehicles = [_make_vehicle("A-231", 1500)]
    out, _ = enrich_with_route_id(vehicles, mapping)
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
    out, _ = enrich_with_route_id(vehicles, mapping)
    assert out[0].route_id == EXPECTED_PK_FOR_HAT["15B"]


def test_empty_vehicles_list():
    mapping = _mapping(**{"A-231": [_interval(1000, 2000, "29B")]})
    out, dropped = enrich_with_route_id([], mapping)
    assert out == []
    assert dropped == 0


def test_input_vehicles_not_mutated():
    mapping = _mapping(**{"A-231": [_interval(1000, 2000, "29B")]})
    original = _make_vehicle("A-231", 1500)
    original = original.model_copy(update={"route_id": "PRESET"})
    vehicles = [original]

    out, _ = enrich_with_route_id(vehicles, mapping)

    assert vehicles[0].route_id == "PRESET"
    assert out[0].route_id == EXPECTED_PK_FOR_HAT["29B"]
    assert id(vehicles[0]) != id(out[0])


def test_corrupt_mapping_missing_by_kapi_key():
    mapping = {"active_routes": ["29B"]}  # no by_kapi, no snapshot_date
    vehicles = [
        _make_vehicle("A-231", 1500),
        _make_vehicle("X-999", 1500),
    ]
    out, _ = enrich_with_route_id(vehicles, mapping)
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
    out, _ = enrich_with_route_id(vehicles, mapping)
    assert out[0].route_id == EXPECTED_PK_FOR_HAT["500T"]


def test_next_day_after_4am_no_overnight_bump():
    """Same mapping as above but vehicle ts = Saturday 05:00 IST → hour >= 4,
    no overnight bump → base_sec = 18000 < start_sec 82800 → no match."""
    mapping = _mapping_with(
        snapshot_date="2026-04-24",
        snapshot_day_type="weekday",
        by_kapi={"A-231": [_interval(82800, 90000, "500T")]},
    )
    vehicles = [_make_vehicle_local("A-231", "2026-04-25T05:00:00+03:00")]
    out, _ = enrich_with_route_id(vehicles, mapping)
    assert out[0].route_id is None


def test_snapshot_date_missing_defensive():
    """No snapshot_date in mapping → overnight check short-circuits to False;
    bisect still works on base_sec."""
    mapping = {
        "by_kapi": {"A-231": [_interval(1000, 2000, "29B")]},
        "route_id_by_short_name": {"29B": EXPECTED_PK_FOR_HAT["29B"]},
        # no snapshot_date, no snapshot_day_type
    }
    vehicles = [_make_vehicle("A-231", 1500)]
    out, _ = enrich_with_route_id(vehicles, mapping)
    assert out[0].route_id == EXPECTED_PK_FOR_HAT["29B"]


def test_snapshot_day_type_missing_defensive():
    """snapshot_date present, snapshot_day_type absent. Overnight check still
    works (only depends on snapshot_date), bisect proceeds normally."""
    mapping = {
        "snapshot_date": TEST_DATE.isoformat(),
        "by_kapi": {"A-231": [_interval(1000, 2000, "29B")]},
        "route_id_by_short_name": {"29B": EXPECTED_PK_FOR_HAT["29B"]},
    }
    vehicles = [_make_vehicle("A-231", 1500)]
    out, _ = enrich_with_route_id(vehicles, mapping)
    assert out[0].route_id == EXPECTED_PK_FOR_HAT["29B"]


# --- 2026-05-02 stale vehicle.timestamp filter -----------------------------


def test_stale_vehicle_timestamp_returns_none():
    """drift > 180s → mapped vehicle demoted to None, counter increments."""
    mapping = _mapping(**{"A-231": [_interval(1000, 2000, "29B")]})
    vehicle = _make_vehicle("A-231", 1500)
    # vehicle.timestamp = TEST midnight + 1500s; reference 200s ahead → drift=200s.
    reference_now = vehicle.timestamp + timedelta(seconds=200)
    out, dropped = enrich_with_route_id(
        [vehicle], mapping, reference_now=reference_now,
    )
    assert out[0].route_id is None
    assert dropped == 1


def test_fresh_vehicle_timestamp_normal_mapping():
    """drift < 180s → bisect result preserved, counter stays 0."""
    mapping = _mapping(**{"A-231": [_interval(1000, 2000, "29B")]})
    vehicle = _make_vehicle("A-231", 1500)
    reference_now = vehicle.timestamp + timedelta(seconds=30)
    out, dropped = enrich_with_route_id(
        [vehicle], mapping, reference_now=reference_now,
    )
    assert out[0].route_id == EXPECTED_PK_FOR_HAT["29B"]
    assert dropped == 0


def test_future_drift_also_dropped():
    """vehicle.timestamp 200s in the future of reference_now → abs() catches
    it. Real-world case: İETT clock-sync errors (~%5 of fleet)."""
    mapping = _mapping(**{"A-231": [_interval(1000, 2000, "29B")]})
    vehicle = _make_vehicle("A-231", 1500)
    reference_now = vehicle.timestamp - timedelta(seconds=200)
    out, dropped = enrich_with_route_id(
        [vehicle], mapping, reference_now=reference_now,
    )
    assert out[0].route_id is None
    assert dropped == 1


def test_reference_now_none_disables_stale_check():
    """Backward-compat: pre-2026-05-02 callers (default kw) keep old behavior,
    no drop even when the timestamp is years off."""
    mapping = _mapping(**{"A-231": [_interval(1000, 2000, "29B")]})
    vehicle = _make_vehicle("A-231", 1500)
    out, dropped = enrich_with_route_id([vehicle], mapping)
    assert out[0].route_id == EXPECTED_PK_FOR_HAT["29B"]
    assert dropped == 0


# --- KM5-a: IETT_BUS_MAPPING_ENABLED flag ---------------------------------


def test_flag_disabled_returns_route_id_none(settings):
    """v0.8.0 default davranışı: flag kapalıyken bisect path tamamen
    atlanır, tüm vehicle'lar route_id=None ile döner."""
    settings.IETT_BUS_MAPPING_ENABLED = False
    mapping = _mapping(**{"A-231": [_interval(1000, 2000, "29B")]})
    vehicles = [
        _make_vehicle("A-231", 1500),  # mapping bisect içine düşerdi
        _make_vehicle("X-999", 1500),  # mapping'de yok zaten
    ]
    out, dropped = enrich_with_route_id(vehicles, mapping)
    assert [v.route_id for v in out] == [None, None]
    assert dropped == 0


def test_flag_disabled_preserves_input_immutability(settings):
    """Flag kapalı path da pure: input vehicle list mutate edilmez."""
    settings.IETT_BUS_MAPPING_ENABLED = False
    mapping = _mapping(**{"A-231": [_interval(1000, 2000, "29B")]})
    original = _make_vehicle("A-231", 1500).model_copy(update={"route_id": "PRESET"})
    vehicles = [original]
    out, _ = enrich_with_route_id(vehicles, mapping)
    assert vehicles[0].route_id == "PRESET"
    assert out[0].route_id is None
    assert id(vehicles[0]) != id(out[0])


def test_flag_disabled_does_not_drop_stale_vehicles(settings):
    """Flag kapalıyken stale-timestamp filter de tetiklenmez (route_id
    zaten None, drift check skip). stale_dropped counter 0 kalır →
    heartbeat ``stats:stale_vehicle_dropped_count`` sıfır yazılır."""
    settings.IETT_BUS_MAPPING_ENABLED = False
    mapping = _mapping(**{"A-231": [_interval(1000, 2000, "29B")]})
    vehicle = _make_vehicle("A-231", 1500)
    reference_now = vehicle.timestamp + timedelta(seconds=600)  # +10dk drift
    out, dropped = enrich_with_route_id(
        [vehicle], mapping, reference_now=reference_now,
    )
    assert out[0].route_id is None
    assert dropped == 0


def test_flag_enabled_default_in_module_uses_mapping():
    """Sanity: autouse fixture flag=True yaptığında inherited testlerin
    eski mapping path çalışıyor — hibernation davranışı garanti."""
    mapping = _mapping(**{"A-231": [_interval(1000, 2000, "29B")]})
    out, _ = enrich_with_route_id([_make_vehicle("A-231", 1500)], mapping)
    assert out[0].route_id == EXPECTED_PK_FOR_HAT["29B"]


# --- KM5-e.1: vehicle.is_metrobus categorize (B yolundan dönüş) ----------


def test_flag_disabled_sets_is_metrobus_for_metrobus_kapi(settings):
    """Flag kapalıyken bile mapping cache lookup'ı kategorize için yapılır:
    KapiNo'nun aktif görevi bir metrobüs SHATKODU ise is_metrobus=True
    set edilir. route_id yine None (KM5-a sözleşmesi korunur)."""
    settings.IETT_BUS_MAPPING_ENABLED = False
    mapping = _mapping(**{"M-3090": [_interval(1000, 2000, "34BZ")]})
    out, _ = enrich_with_route_id([_make_vehicle("M-3090", 1500)], mapping)
    assert out[0].is_metrobus is True
    assert out[0].route_id is None


def test_flag_disabled_sets_is_metrobus_false_for_normal_bus(settings):
    """Normal İETT bus SHATKODU (29B) METROBUS_SHORT_NAMES dışında →
    is_metrobus=False; aynı path, aynı bisect, sadece whitelist farkı."""
    settings.IETT_BUS_MAPPING_ENABLED = False
    mapping = _mapping(**{"A-231": [_interval(1000, 2000, "29B")]})
    out, _ = enrich_with_route_id([_make_vehicle("A-231", 1500)], mapping)
    assert out[0].is_metrobus is False
    assert out[0].route_id is None


def test_flag_disabled_is_metrobus_false_when_kapi_not_in_mapping(settings):
    """KapiNo by_kapi'de yok → bisect skip → is_metrobus=False (defansif).
    Mapping cache miss yokluğu metrobüs sayılmaz, "tip bilinmiyor" durumu."""
    settings.IETT_BUS_MAPPING_ENABLED = False
    mapping = _mapping(**{"A-231": [_interval(1000, 2000, "34BZ")]})
    out, _ = enrich_with_route_id([_make_vehicle("X-999", 1500)], mapping)
    assert out[0].is_metrobus is False
    assert out[0].route_id is None


def test_flag_disabled_is_metrobus_false_when_mapping_empty(settings):
    """by_kapi yok / mapping boş dict → tüm vehicle'lar is_metrobus=False.
    Cache miss / refresh hatası senaryosu defansif handle edilir."""
    settings.IETT_BUS_MAPPING_ENABLED = False
    out, _ = enrich_with_route_id([_make_vehicle("M-3090", 1500)], {})
    assert out[0].is_metrobus is False
    assert out[0].route_id is None


def test_flag_enabled_also_sets_is_metrobus(settings):
    """Hibernation path (flag açık) kategorize bilgisini de üretir;
    mapping bisect lookup'ın yan ürünü, ek cost yok."""
    settings.IETT_BUS_MAPPING_ENABLED = True
    mapping = _mapping(**{"M-3090": [_interval(1000, 2000, "34BZ")]})
    out, _ = enrich_with_route_id([_make_vehicle("M-3090", 1500)], mapping)
    assert out[0].is_metrobus is True
    # Flag açık olduğu için route_id de stamp'lendi (hibernation)
    assert out[0].route_id == EXPECTED_PK_FOR_HAT["34BZ"]
