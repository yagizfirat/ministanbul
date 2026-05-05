"""Spatial sanity check for vehicle-to-route mapping.

The mapping cache (a time-bound KapiNo → SHATKODU table) only says
which line a vehicle SHOULD be running. A vehicle can be returning
to the depot or on break, in which case the mapping still labels it
as if it were on the route. This module closes the gap: when a vehicle
sits more than THRESHOLD metres away from the shape geometry of its
mapped route, route_id is demoted to None.

Cache strategy: lazy module-level dict. The first
``get_route_shape_cache()`` call loads every active route's shape
into a ``short_name → np.ndarray[(lat, lon)]`` map. Cold start is on
the order of seconds; subsequent ticks are O(0).

Per-vehicle cost: a numpy vectorized haversine across the whole shape
pool — under 1 ms per ~100-point shape.

Caveat: the live İETT feed currently has no shapes for bus routes.
Public-feed routes (rail/ferry) all have shapes. The check skips on
cache miss (trusts the mapping) — see the spatial_check loop in
tasks.py for details.
"""
from __future__ import annotations

import logging

import numpy as np

logger = logging.getLogger(__name__)

SPATIAL_CHECK_THRESHOLD_METERS = 500.0
EARTH_RADIUS_METERS = 6_371_000.0

_route_shape_cache: dict[str, np.ndarray] | None = None


def haversine_meters(
    lat1: float | np.ndarray,
    lon1: float | np.ndarray,
    lat2: float | np.ndarray,
    lon2: float | np.ndarray,
) -> float | np.ndarray:
    """Haversine great-circle distance in meters. Scalar veya np.ndarray
    argümanlar kabul eder (vectorized). Aynı shape broadcast'i için
    standard numpy semantik."""
    phi1 = np.radians(lat1)
    phi2 = np.radians(lat2)
    dphi = np.radians(np.subtract(lat2, lat1))
    dlam = np.radians(np.subtract(lon2, lon1))
    a = np.sin(dphi / 2.0) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlam / 2.0) ** 2
    return EARTH_RADIUS_METERS * 2.0 * np.arcsin(np.sqrt(a))


def is_vehicle_near_route(
    lat: float,
    lon: float,
    shape_arr: np.ndarray,
    threshold: float | None = None,
) -> bool:
    """Araç pozisyonu, route'un shape pool'undaki en yakın noktaya
    threshold mesafesi içinde mi. shape_arr: (N, 2) np.ndarray, her
    satır (lat, lon). threshold None → SPATIAL_CHECK_THRESHOLD_METERS.

    Boş shape_arr → False (defansif: shape kaynağı eksikse araç
    hat üzerinde sayılmaz)."""
    if threshold is None:
        threshold = SPATIAL_CHECK_THRESHOLD_METERS
    if shape_arr.size == 0:
        return False
    distances = haversine_meters(lat, lon, shape_arr[:, 0], shape_arr[:, 1])
    return float(distances.min()) <= threshold


def build_route_shape_cache() -> dict[str, np.ndarray]:
    """GTFS Route + Trip + Shape join: her ``short_name`` için tüm
    trip'lerinin shape geometrilerinden gelen (lat, lon) noktalarını
    dedupe edip np.ndarray olarak topla.

    Bir ``short_name`` birden fazla ``route_id``'ye karşılık gelebilir
    (29B/55T örneğinde 7 farklı GTFS route_id gözlemlendi). Hepsinin
    trip'leri tek havuza akar — UI seviyesinde "29B" tek hat, GTFS
    seviyesinde varyant ayrımı önemsiz."""
    # Lokal import: Django settings hazır olmadan modül yüklenirse
    # apps.gtfs.models import patlardı; lazy build sırasında çağrılır.
    from apps.gtfs.models import Route

    cache: dict[str, np.ndarray] = {}
    short_names = (
        Route.objects.exclude(short_name="")
        .values_list("short_name", flat=True)
        .distinct()
    )
    for short_name in short_names:
        coords: set[tuple[float, float]] = set()
        shapes = (
            Route.objects.filter(short_name=short_name)
            .filter(trips__shape__isnull=False)
            .values_list("trips__shape__geometry", flat=True)
            .distinct()
        )
        for geom in shapes:
            if geom is None:
                continue
            # GeoDjango LineString.coords → ((lon, lat), (lon, lat), ...).
            # Spatial check için (lat, lon) tutarlılığı şart.
            for lon, lat in geom.coords:
                coords.add((lat, lon))
        if coords:
            cache[short_name] = np.array(sorted(coords), dtype=np.float64)
    logger.info(
        "build_route_shape_cache: %d short_names cached, %d toplam nokta",
        len(cache),
        sum(arr.shape[0] for arr in cache.values()),
    )
    return cache


def get_route_shape_cache() -> dict[str, np.ndarray]:
    """Lazy module-level cache accessor. İlk çağrıda build, sonraki
    çağrılarda re-use. Test'lerde monkeypatch ile direkt değiştirilir
    (örn. _route_shape_cache = {"29B": np.array(...)})."""
    global _route_shape_cache
    if _route_shape_cache is None:
        _route_shape_cache = build_route_shape_cache()
    return _route_shape_cache
