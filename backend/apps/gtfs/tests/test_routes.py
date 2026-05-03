"""Tests for /api/routes/ endpoint — KM5-b is_metrobus categorize flag.

Spec §3.3 (v0.8.0): metrobüs whitelist semantiği "mapping exception" değil,
sadece frontend kategorize (antrasit gri ayrımı). RouteSerializer.is_metrobus
short_name in settings.METROBUS_SHORT_NAMES kontrolüne dayanır; agency=İETT
kontrolü gereksiz çünkü 34-prefix'li short_name'ler İETT'ye özel
(Spec §3.3 discovery query, 2026-04-24).
"""
from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.gtfs.models import Agency, Route


@pytest.fixture
def routes_data(db):
    """Three routes covering the categorize matrix:
      - 34BZ: metrobüs whitelist member        → is_metrobus=True
      - 29B:  normal İETT bus (route_type=3)   → is_metrobus=False
      - M2:   metro (route_type=1)             → is_metrobus=False
    """
    iett = Agency.objects.create(
        agency_id="1", name="IETT", url="https://www.iett.istanbul",
        timezone="Europe/Istanbul",
    )
    public = Agency.objects.create(
        agency_id="public", name="Public Transit", url="https://example.com",
        timezone="Europe/Istanbul",
    )
    metrobus = Route.objects.create(
        route_id="iett:metrobus-34bz", agency=iett,
        short_name="34BZ", long_name="ZINCIRLIKUYU - B.SONDURAK", route_type=3,
    )
    bus = Route.objects.create(
        route_id="iett:bus-29b", agency=iett,
        short_name="29B", long_name="4.LEVENT - FATIH SULTAN MEHMET", route_type=3,
    )
    metro = Route.objects.create(
        route_id="public:m2", agency=public,
        short_name="M2", long_name="YENIKAPI - HACIOSMAN", route_type=1,
    )
    return {"metrobus": metrobus, "bus": bus, "metro": metro}


def _get_route(client: APIClient, route_id: str) -> dict:
    url = reverse("route-detail", args=[route_id])
    resp = client.get(url)
    assert resp.status_code == 200, resp.content
    return resp.json()


def test_metrobus_short_name_returns_is_metrobus_true(routes_data):
    """METROBUS_SHORT_NAMES içindeki bir hat (34BZ) is_metrobus=True döner."""
    body = _get_route(APIClient(), "iett:metrobus-34bz")
    assert body["short_name"] == "34BZ"
    assert body["is_metrobus"] is True


def test_normal_bus_short_name_returns_is_metrobus_false(routes_data):
    """METROBUS_SHORT_NAMES dışındaki İETT bus (29B) is_metrobus=False döner —
    aynı route_type=3 ama whitelist eşi yok."""
    body = _get_route(APIClient(), "iett:bus-29b")
    assert body["short_name"] == "29B"
    assert body["is_metrobus"] is False


def test_rail_short_name_returns_is_metrobus_false(routes_data):
    """Raylı sistem (M2) is_metrobus=False — kategori dışı, default değer."""
    body = _get_route(APIClient(), "public:m2")
    assert body["short_name"] == "M2"
    assert body["is_metrobus"] is False


def test_list_endpoint_includes_is_metrobus_for_every_row(routes_data):
    """List endpoint (?mode=bus) her bus row'unda is_metrobus field'ı döner.
    Hem true hem false değerini gerçekten ayırt edebiliyor mu (regression
    guard: SerializerMethodField evaluation list serialization'da da çalışır)."""
    resp = APIClient().get("/api/routes/?mode=bus")
    assert resp.status_code == 200
    items = resp.json()["results"]
    by_short = {r["short_name"]: r for r in items}
    assert "34BZ" in by_short and by_short["34BZ"]["is_metrobus"] is True
    assert "29B" in by_short and by_short["29B"]["is_metrobus"] is False


def test_is_metrobus_uses_settings_frozenset(routes_data, settings):
    """Override fixture: settings.METROBUS_SHORT_NAMES daraltılırsa eski
    metrobüs hattı is_metrobus=False'a düşer. Kaynak runtime settings
    okuması (mapping cache değil) — değişiklik anında yansır."""
    settings.METROBUS_SHORT_NAMES = frozenset({"34"})  # 34BZ artık dışarıda
    body = _get_route(APIClient(), "iett:metrobus-34bz")
    assert body["is_metrobus"] is False
