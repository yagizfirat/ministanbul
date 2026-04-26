"""Unit tests for vehicle-to-route spatial sanity check (Faz 3 6h-i-3).

5 test invariant:
  1-2: haversine matematik doğruluğu (zero + known distance)
  3-5: is_vehicle_near_route threshold davranışı (inside / outside /
       boundary çift assertion)

build_route_shape_cache + get_route_shape_cache testleri burada YOK
— DB join semantiği 6h-i-4 integration test'lerinde gerçek tasks.py
akışıyla doğrulanır.
"""
from __future__ import annotations

import numpy as np
import pytest

from apps.realtime.spatial import (
    haversine_meters,
    is_vehicle_near_route,
)


# --- 1. haversine: aynı nokta = 0m ----------------------------------------


def test_haversine_zero_distance():
    """Aynı koordinat → tam 0m. Floating-point hassasiyeti kontrolü."""
    assert haversine_meters(41.0, 29.0, 41.0, 29.0) == pytest.approx(0.0, abs=1e-6)


# --- 2. haversine: bilinen mesafe (İstanbul ↔ Ankara ~352km) -------------


def test_haversine_known_distance():
    """Sultanahmet (41.0082, 28.9784) ↔ Kızılay (39.9334, 32.8597)
    great-circle ≈ 352km. ±%1 tolerans (~3.5km)."""
    distance = haversine_meters(41.0082, 28.9784, 39.9334, 32.8597)
    assert distance == pytest.approx(352_000.0, rel=0.01)


# --- 3. is_vehicle_near_route: shape üstünde → True -----------------------


def test_is_vehicle_near_route_inside_threshold():
    """Vehicle shape'in TAM ÜZERİNDE → 0m mesafe → True."""
    shape = np.array([[41.0, 29.0], [41.01, 29.01]])
    assert is_vehicle_near_route(41.0, 29.0, shape) is True


# --- 4. is_vehicle_near_route: 1km uzakta → False -------------------------


def test_is_vehicle_near_route_outside_threshold():
    """Vehicle shape'ten ~1km uzakta (lat farkı 0.009° ≈ 1002m) →
    threshold 500m'i aşıyor → False."""
    shape = np.array([[41.0, 29.0]])
    assert is_vehicle_near_route(41.009, 29.0, shape) is False


# --- 5. is_vehicle_near_route: boundary'nin her iki yanı ------------------


def test_is_vehicle_near_route_at_boundary():
    """Threshold (500m default) sınırının her iki yanı tek testte —
    boundary doğruluğunu çift assertion ile sıkıştırır.
    Lat 1° ≈ 111.32km, 500m ≈ 0.00449°."""
    shape = np.array([[41.0, 29.0]])
    # ~499m içeride → True
    assert is_vehicle_near_route(41.00448, 29.0, shape) is True
    # ~501m dışarıda → False
    assert is_vehicle_near_route(41.00450, 29.0, shape) is False
