"""Tests for /api/shapes/{shape_id}/ endpoint (Faz 5 KM3-a fix)."""
from __future__ import annotations

import pytest
from django.contrib.gis.geos import LineString
from rest_framework.test import APIClient

from apps.gtfs.models import Shape


@pytest.fixture
def shape_fixture(db) -> Shape:
    return Shape.objects.create(
        shape_id="TEST_SHAPE_42",
        geometry=LineString((29.0, 41.0), (29.01, 41.0), (29.01, 41.01)),
    )


@pytest.fixture
def client() -> APIClient:
    return APIClient()


def test_shape_detail_returns_geojson(client, shape_fixture):
    r = client.get(f"/api/shapes/{shape_fixture.shape_id}/")
    assert r.status_code == 200
    data = r.json()
    assert data["type"] == "Feature"
    assert data["geometry"]["type"] == "LineString"
    assert data["properties"]["shape_id"] == shape_fixture.shape_id
    assert len(data["geometry"]["coordinates"]) == 3


def test_shape_detail_404(client, db):
    r = client.get("/api/shapes/nonexistent/")
    assert r.status_code == 404


def test_shape_detail_cache_header(client, shape_fixture):
    r = client.get(f"/api/shapes/{shape_fixture.shape_id}/")
    cc = r.headers.get("Cache-Control", "")
    assert "max-age=86400" in cc
    assert "public" in cc
