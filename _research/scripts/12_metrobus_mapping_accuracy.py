"""β-lite metrobüs mapping doğruluğu ölçümü — KM5-a karar gate'i.

Hipotez: METROBUS_SHORT_NAMES (10 hat) için mapping doğru olmalı, çünkü
metrobüs koridoru sabit ve izole. SPEC §3.3 + Ek A.18 KM5-b risk notu
"5 dk spot kontrol" gerektiriyor.

Yöntem:
  1. `iett:mapping:current`'tan vehicles:all'a bak; route_id metrobüs
     short_name'lerine işaret eden vehicle'ları al.
  2. Her metrobüs short_name için en uzun stop_times sequence'a sahip
     trip'i seç (Spec Ek A.4: shape_id boş → straight-line türetme).
     Bu trip'in stop sırası straight-line LineString = kanonik koridor.
  3. PostGIS ST_Distance(point::geography, polyline::geography) ile metre
     cinsi dik mesafe ölç.
  4. Eşikler: <200m doğru, 200-500m şüpheli, >500m yanlış.
  5. Hat bazında + toplam istatistik (median, p90, p99, %wrong, %suspicious).

Karşılaştırma için aynı yöntem normal İETT bus'a uygulanır (--include-bus).
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from collections import defaultdict
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
django.setup()

import redis
from django.conf import settings
from django.contrib.gis.geos import LineString, Point
from django.db.models import Count

from apps.gtfs.models import Route, Stop, StopTime, Trip


METROBUS = ["34", "34A", "34AS", "34B", "34BZ", "34C", "34G", "34T", "34U", "34Z"]
THRESHOLD_OK = 200
THRESHOLD_SUSP = 500


def pick_canonical_polyline(short_name: str):
    """For a given short_name, return (trip_id, LineString, num_stops, route_long_name)
    where the trip has the most stops among all variants (canonical corridor).
    Returns None if no trip with stops is found.
    """
    routes = Route.objects.filter(short_name=short_name, agency__agency_id="1")
    trip_qs = (
        Trip.objects.filter(route__in=routes)
        .annotate(n=Count("stop_times"))
        .filter(n__gt=1)
        .order_by("-n")
    )
    trip = trip_qs.first()
    if not trip:
        return None
    stop_times = (
        StopTime.objects.filter(trip=trip)
        .order_by("stop_sequence")
        .select_related("stop")
    )
    coords = []
    for st in stop_times:
        if st.stop and st.stop.location:
            coords.append((st.stop.location.x, st.stop.location.y))
    if len(coords) < 2:
        return None
    line = LineString(coords, srid=4326)
    return trip, line, len(coords), trip.route.long_name


def vehicles_for_short_name(short_name: str, mapping: dict, snap: dict) -> list[dict]:
    """Vehicle'lar route_id stamped'i metrobüs hattına işaret edenler."""
    rsn = mapping["route_id_by_short_name"]
    short_route_id = rsn.get(short_name)
    if not short_route_id:
        return []
    # Tüm route_id varyantları (gidiş/dönüş/varyant) için toplam atama
    all_route_ids = set(
        Route.objects.filter(short_name=short_name, agency__agency_id="1")
        .values_list("route_id", flat=True)
    )
    return [
        v for v in snap["vehicles"]
        if v.get("route_id") and v["route_id"] in all_route_ids
    ]


def measure_distances(vehicles: list[dict], polyline: LineString) -> list[tuple[str, float]]:
    """ST_Distance(point::geography, polyline::geography) — m."""
    if not vehicles:
        return []
    # Tek query'de batch ST_Distance: raw SQL yerine Django ORM annotate
    # GEOSGeometry üzerinden Python tarafında yaklaşık değer almak yerine
    # PostgreSQL'e gönderiyoruz.
    from django.contrib.gis.db.models.functions import Distance
    from django.db import connection
    from django.db.models import F
    # Hafıza için: vehicle list'ini tabloya yazmadan inline yapacağız
    # Çözüm: cursor.execute ile prepared statement
    with connection.cursor() as cur:
        results = []
        # Bulk insert yapmadan tek tek (vehicle sayısı düşük: max ~500)
        for v in vehicles:
            cur.execute(
                """
                SELECT ST_Distance(
                    ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                    ST_GeomFromText(%s, 4326)::geography
                )
                """,
                [v["lon"], v["lat"], polyline.wkt],
            )
            d = cur.fetchone()[0]
            results.append((v["id"], float(d)))
    return results


def percentile(sorted_values: list[float], p: float) -> float:
    if not sorted_values:
        return float("nan")
    k = (len(sorted_values) - 1) * p
    f, c = int(k), min(int(k) + 1, len(sorted_values) - 1)
    return sorted_values[f] + (sorted_values[c] - sorted_values[f]) * (k - f)


def stats_for(distances: list[float]) -> dict:
    n = len(distances)
    if n == 0:
        return {"n": 0}
    s = sorted(distances)
    ok = sum(1 for d in s if d < THRESHOLD_OK)
    susp = sum(1 for d in s if THRESHOLD_OK <= d < THRESHOLD_SUSP)
    wrong = sum(1 for d in s if d >= THRESHOLD_SUSP)
    return {
        "n": n,
        "median_m": round(statistics.median(s), 0),
        "p90_m": round(percentile(s, 0.90), 0),
        "p99_m": round(percentile(s, 0.99), 0),
        "max_m": round(s[-1], 0),
        "ok_pct": round(ok / n * 100, 1),
        "suspicious_pct": round(susp / n * 100, 1),
        "wrong_pct": round(wrong / n * 100, 1),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--include-bus", action="store_true",
                    help="Normal İETT bus için aynı yöntemle β karşılaştırma çalıştır")
    ap.add_argument("--bus-sample", type=int, default=2000,
                    help="Normal bus için sample limiti (varsayılan 2000)")
    args = ap.parse_args()

    r = redis.Redis.from_url(settings.REDIS_URL)
    snap = json.loads(r.get("vehicles:all"))
    mapping = json.loads(r.get("iett:mapping:current"))

    print(f"snapshot ts: {snap['timestamp']}")
    print(f"snapshot vehicles={snap['vehicle_count']}, mapped={snap['mapped_count']}")
    print(f"mapping snapshot_date: {mapping['snapshot_date']}")
    print()

    # ---------- Metrobüs ----------
    print("=" * 70)
    print("METROBÜS — β-lite ölçümü")
    print("=" * 70)
    per_route = []
    all_distances_metrobus = []
    variant_notes = []

    for sn in METROBUS:
        info = pick_canonical_polyline(sn)
        if info is None:
            variant_notes.append(f"{sn}: trip yok (route'lar trip'siz)")
            per_route.append({
                "short_name": sn,
                "polyline_trip": None,
                "polyline_stops": 0,
                "stats": {"n": 0, "note": "trip yok"},
            })
            continue
        trip, line, num_stops, long_name = info
        variant_notes.append(
            f"{sn}: trip={trip.trip_id} stops={num_stops} long_name={long_name!r}"
        )

        vehs = vehicles_for_short_name(sn, mapping, snap)
        if not vehs:
            per_route.append({
                "short_name": sn,
                "polyline_trip": trip.trip_id,
                "polyline_stops": num_stops,
                "stats": {"n": 0, "note": "atanmış vehicle yok"},
            })
            continue

        dists = measure_distances(vehs, line)
        only_d = [d for _, d in dists]
        all_distances_metrobus.extend(only_d)
        per_route.append({
            "short_name": sn,
            "polyline_trip": trip.trip_id,
            "polyline_stops": num_stops,
            "stats": stats_for(only_d),
            "worst": [(vid, round(d, 0)) for vid, d in sorted(dists, key=lambda x: -x[1])[:3]],
        })

    # Tablo
    print(f"\n{'hat':>6} | {'n':>4} | {'med':>6} | {'p90':>6} | {'p99':>6} | "
          f"{'%ok':>5} | {'%susp':>6} | {'%wrong':>6}")
    print("-" * 70)
    for row in per_route:
        s = row["stats"]
        if s.get("n") == 0:
            print(f"{row['short_name']:>6} | {'-':>4} | {'-':>6} | {'-':>6} | {'-':>6} | "
                  f"{'-':>5} | {'-':>6} | {'-':>6}  ({s.get('note','-')})")
        else:
            print(f"{row['short_name']:>6} | {s['n']:>4} | {s['median_m']:>6.0f} | "
                  f"{s['p90_m']:>6.0f} | {s['p99_m']:>6.0f} | "
                  f"{s['ok_pct']:>5.1f} | {s['suspicious_pct']:>6.1f} | {s['wrong_pct']:>6.1f}")

    # Toplam
    total = stats_for(all_distances_metrobus)
    print(f"\nTOPLAM metrobüs: {total}")

    # Variant notları
    print(f"\nVariant seçim notları:")
    for note in variant_notes:
        print(f"  - {note}")

    # Worst per route
    print(f"\nHat başına worst-3 (KapiNo, mesafe_m):")
    for row in per_route:
        if "worst" in row:
            print(f"  {row['short_name']}: {row['worst']}")

    # ---------- Normal bus karşılaştırma ----------
    bus_total = None
    if args.include_bus:
        print()
        print("=" * 70)
        print(f"NORMAL İETT BUS — β karşılaştırma (sample={args.bus_sample})")
        print("=" * 70)
        # Tüm metrobüs olmayan İETT bus mapped vehicle'ları
        metrobus_route_ids = set(
            Route.objects.filter(short_name__in=METROBUS, agency__agency_id="1")
            .values_list("route_id", flat=True)
        )
        bus_vehicles = [
            v for v in snap["vehicles"]
            if v.get("route_id") and v["route_id"] not in metrobus_route_ids
            and v["route_id"].startswith("iett:")
        ]
        bus_vehicles = bus_vehicles[: args.bus_sample]
        print(f"sample size: {len(bus_vehicles)}")

        # Her vehicle için: kendi route_id'sinin short_name'ini bul, o short_name'in
        # canonical polyline'ını al, ST_Distance ölç.
        rsn_inv = {rid: sn for sn, rid in mapping["route_id_by_short_name"].items()}
        # Cache polyline by short_name to amortize
        poly_cache: dict[str, LineString] = {}
        bus_distances = []
        skipped_no_poly = 0
        for v in bus_vehicles:
            sn = rsn_inv.get(v["route_id"])
            if not sn:
                skipped_no_poly += 1
                continue
            if sn not in poly_cache:
                info = pick_canonical_polyline(sn)
                if info is None:
                    poly_cache[sn] = None
                else:
                    poly_cache[sn] = info[1]
            line = poly_cache[sn]
            if line is None:
                skipped_no_poly += 1
                continue
            dists = measure_distances([v], line)
            if dists:
                bus_distances.append(dists[0][1])

        print(f"polyline türetilemedi (skipped): {skipped_no_poly}")
        bus_total = stats_for(bus_distances)
        print(f"\nTOPLAM normal bus: {bus_total}")

    # JSON çıktı
    out = {
        "snapshot_ts": snap["timestamp"],
        "mapping_snapshot_date": mapping["snapshot_date"],
        "thresholds": {"ok_m": THRESHOLD_OK, "suspicious_m": THRESHOLD_SUSP},
        "metrobus": {
            "per_route": per_route,
            "total": total,
            "variant_notes": variant_notes,
        },
    }
    if bus_total is not None:
        out["normal_bus"] = {
            "sample_size": len(bus_vehicles),
            "skipped_no_polyline": skipped_no_poly,
            "total": bus_total,
        }

    out_path = Path(__file__).parent / "12_metrobus_mapping_accuracy_result.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
