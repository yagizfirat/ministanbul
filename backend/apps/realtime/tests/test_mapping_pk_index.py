"""Tests for ``build_mapping``'s ``route_id_by_short_name`` PK index
(Yol B — frontend route_id contract alignment).

The PK index translates SHATKODU (e.g. ``"29B"``) to GTFS Route.route_id
(``"iett:1562"``) so vehicle.route_id matches the frontend RouteStore
key. Selection policy: agency=IETT, route_type=3 (bus), tie-breaker
``ORDER BY route_id ASC LIMIT 1`` per short_name.
"""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from apps.gtfs.models import Agency, Route
from apps.realtime.enrich import enrich_with_route_id
from apps.realtime.mapping import build_mapping
from apps.realtime.schemas import IettArsivGorev, VehiclePosition

ISTANBUL_TZ = ZoneInfo("Europe/Istanbul")
SNAPSHOT_DATE = date(2026, 4, 22)


def _gorev(kapi_no: str, hat_kodu: str) -> IettArsivGorev:
    return IettArsivGorev(
        kapi_no=kapi_no,
        hat_kodu=hat_kodu,
        guzergah_kodu=f"{hat_kodu}_G_D0",
        start_time=datetime(2026, 4, 22, 5, tzinfo=ISTANBUL_TZ),
        end_time=datetime(2026, 4, 22, 6, tzinfo=ISTANBUL_TZ),
        gorev_durum="T",
    )


@pytest.fixture
def iett_agency(db) -> Agency:
    return Agency.objects.create(
        agency_id="1",
        name="IETT",
        url="https://www.iett.istanbul",
    )


@pytest.fixture
def other_agency(db) -> Agency:
    """Non-IETT agency for β-filter exclusion tests."""
    return Agency.objects.create(
        agency_id="11",
        name="Metro İstanbul",
        url="https://www.metro.istanbul",
    )


@pytest.mark.django_db
def test_route_id_by_short_name_populated(iett_agency):
    """Each active SHATKODU maps to its IETT bus PK in the mapping output."""
    Route.objects.create(
        route_id="iett:1562", agency=iett_agency, short_name="29B",
        long_name="Bostancı - Kadıköy", route_type=Route.ROUTE_TYPE_BUS,
    )
    Route.objects.create(
        route_id="iett:23965", agency=iett_agency, short_name="15B",
        long_name="Beşiktaş - Sarıyer", route_type=Route.ROUTE_TYPE_BUS,
    )

    out = build_mapping(
        [_gorev("A-1", "29B"), _gorev("A-2", "15B")],
        SNAPSHOT_DATE, "weekday",
    )

    assert out["route_id_by_short_name"] == {
        "29B": "iett:1562",
        "15B": "iett:23965",
    }


@pytest.mark.django_db
def test_route_id_by_short_name_alphabetical_tiebreaker(iett_agency):
    """When multiple Route rows share a short_name, ORDER BY route_id ASC
    picks ``iett:1562`` over ``iett:5000`` and ``iett:9999`` — lexicographic
    on ``route_id`` (matches Postgres default + Python str sort)."""
    Route.objects.create(
        route_id="iett:9999", agency=iett_agency, short_name="29B",
        long_name="29B variant late", route_type=Route.ROUTE_TYPE_BUS,
    )
    Route.objects.create(
        route_id="iett:1562", agency=iett_agency, short_name="29B",
        long_name="29B canonical", route_type=Route.ROUTE_TYPE_BUS,
    )
    Route.objects.create(
        route_id="iett:5000", agency=iett_agency, short_name="29B",
        long_name="29B variant mid", route_type=Route.ROUTE_TYPE_BUS,
    )

    out = build_mapping([_gorev("A-1", "29B")], SNAPSHOT_DATE, "weekday")

    assert out["route_id_by_short_name"] == {"29B": "iett:1562"}


@pytest.mark.django_db
def test_route_id_by_short_name_excludes_non_iett_and_non_bus(
    iett_agency, other_agency,
):
    """β filter: only agency=IETT AND route_type=3 rows are eligible.
    A metro row sharing the short_name (route_type=1) and an IETT tram row
    (route_type=0) must both be skipped."""
    Route.objects.create(
        route_id="public:1298", agency=other_agency, short_name="29B",
        long_name="Metro impostor", route_type=Route.ROUTE_TYPE_SUBWAY,
    )
    Route.objects.create(
        route_id="iett:9999", agency=iett_agency, short_name="29B",
        long_name="Tram impostor", route_type=Route.ROUTE_TYPE_TRAM,
    )
    Route.objects.create(
        route_id="iett:1562", agency=iett_agency, short_name="29B",
        long_name="29B canonical bus", route_type=Route.ROUTE_TYPE_BUS,
    )

    out = build_mapping([_gorev("A-1", "29B")], SNAPSHOT_DATE, "weekday")

    assert out["route_id_by_short_name"] == {"29B": "iett:1562"}


@pytest.mark.django_db
def test_route_id_by_short_name_orphan_returns_none_in_enrich(iett_agency):
    """If mapping carries a SHATKODU (``"34BZ"``) that has no Route row,
    the PK index omits it; downstream enrich resolves route_id=None for
    vehicles on that hat. Distinct from the kapı-not-in-mapping case."""
    Route.objects.create(
        route_id="iett:1562", agency=iett_agency, short_name="29B",
        long_name="29B", route_type=Route.ROUTE_TYPE_BUS,
    )
    # No Route row for "34BZ" — orphan SHATKODU.

    mapping = build_mapping(
        [_gorev("A-1", "29B"), _gorev("A-2", "34BZ")],
        SNAPSHOT_DATE, "weekday",
    )

    assert "29B" in mapping["route_id_by_short_name"]
    assert "34BZ" not in mapping["route_id_by_short_name"]

    vehicle = VehiclePosition(
        vehicle_id="A-2",
        latitude=41.0, longitude=29.0,
        timestamp=datetime(2026, 4, 22, 5, 30, tzinfo=ISTANBUL_TZ),
        source="iett-soap", mode="bus",
    )
    enriched, _ = enrich_with_route_id([vehicle], mapping)
    assert enriched[0].route_id is None


@pytest.mark.django_db
def test_iett_agency_missing_graceful(caplog):
    """No IETT Agency row at all → defensive fallback: empty PK index,
    no crash, WARNING logged. enrich downstream resolves all to None."""
    # No Agency.objects.create(...) — clean DB.
    out = build_mapping(
        [_gorev("A-1", "29B")], SNAPSHOT_DATE, "weekday",
    )

    assert out["route_id_by_short_name"] == {}
    assert out["active_routes"] == ["29B"]  # by_kapi work still happened

    warns = [
        r for r in caplog.records
        if r.levelno >= 30 and "route_id_by_short_name disabled" in r.getMessage()
    ]
    assert len(warns) == 1
