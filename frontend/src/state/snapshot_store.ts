import { interpolatePosition } from '../simulation/interpolator';
import type { VehicleSnapshot } from '../data/websocket';

export interface Vehicle {
  id: string;
  lat: number;
  lon: number;
  bearing: number | null;
  speed: number;
  route_id: string | null;
  // KM5-e.1: backend kategorize sinyali (Spec §3.3). Optional — eski
  // snapshot'lar veya ileride farklı adapter'lar field'ı taşımayabilir.
  // KM5-e.2 InterpolatedVehicle'a yansıtır, fleet_layer paint expression
  // is_metrobus=true → antrasit gri rendering uygular.
  is_metrobus?: boolean;
}

export interface InterpolatedVehicle {
  id: string;
  lat: number;
  lon: number;
  route_id: string | null;
  // KM5-e.2: backend'den gelen is_metrobus snapshot.push üzerinden
  // taşınır, fleet_layer paint expression antrasit/sarı ayrımı yapar.
  is_metrobus?: boolean;
}

interface ParsedSnapshot {
  dataTime: number;        // ms since epoch (snapshot.timestamp parsed)
  receivedWall: number;    // performance.now() at arrival
  vehicles: Map<string, Vehicle>;
}

const FALLBACK_INTERVAL_MS = 60_000;

export class SnapshotStore {
  private t0: ParsedSnapshot | null = null;
  private t1: ParsedSnapshot | null = null;

  push(raw: VehicleSnapshot): void {
    const next: ParsedSnapshot = {
      dataTime: Date.parse(raw.timestamp),
      receivedWall: performance.now(),
      vehicles: indexVehicles(raw.vehicles as Vehicle[]),
    };
    if (this.t1 === null) {
      this.t0 = next;
      this.t1 = next;
    } else {
      this.t0 = this.t1;
      this.t1 = next;
    }
  }

  getInterpolated(now: number): InterpolatedVehicle[] {
    if (this.t1 === null || this.t0 === null) return [];

    const interval = this.t1.dataTime - this.t0.dataTime;
    const elapsed = now - this.t1.receivedWall;
    const denom = interval > 0 ? interval : FALLBACK_INTERVAL_MS;
    const alpha = clamp(elapsed / denom, 0, 1);

    const out: InterpolatedVehicle[] = [];
    for (const [id, t1Vehicle] of this.t1.vehicles) {
      const t0Vehicle = this.t0.vehicles.get(id) ?? t1Vehicle;
      const pos = interpolatePosition(id, t0Vehicle, t1Vehicle, alpha);
      out.push({
        id,
        lat: pos.lat,
        lon: pos.lon,
        route_id: t1Vehicle.route_id,
        is_metrobus: t1Vehicle.is_metrobus,
      });
    }
    return out;
  }

  // KM5-e.2: panel "İETT Otobüs (n)" / "Metrobüs (n)" sayaçları için.
  // Latest snapshot üzerinden anlık sayım; interpolation aralığında
  // değişmez (set push'ta güncellenir). Snapshot yoksa 0/0.
  countByMetrobus(): { bus: number; metrobus: number } {
    if (this.t1 === null) return { bus: 0, metrobus: 0 };
    let bus = 0;
    let metrobus = 0;
    for (const v of this.t1.vehicles.values()) {
      if (v.is_metrobus) metrobus++;
      else bus++;
    }
    return { bus, metrobus };
  }

  latestTimestamp(): number | null {
    return this.t1?.dataTime ?? null;
  }

  // f-polish-3 madde 3: bus için polyline yok → çift tıklamada
  // vehicle konumlarından bbox hesapla (fallback). Single-route
  // convenience; multi-route için getVehicleBBoxForRoutes.
  getVehicleBBoxForRoute(routeId: string): [number, number, number, number] | null {
    return this.getVehicleBBoxForRoutes([routeId]);
  }

  // f-polish-5: union bbox over multiple route_ids (variant group).
  // Bus 29B = 7 variant route_id; tüm araçların ortak bbox'ı.
  getVehicleBBoxForRoutes(
    routeIds: readonly string[],
  ): [number, number, number, number] | null {
    if (this.t1 === null || routeIds.length === 0) return null;
    const idSet = new Set(routeIds);
    let minLon = Infinity;
    let minLat = Infinity;
    let maxLon = -Infinity;
    let maxLat = -Infinity;
    let count = 0;
    for (const v of this.t1.vehicles.values()) {
      if (v.route_id === null || !idSet.has(v.route_id)) continue;
      if (v.lon < minLon) minLon = v.lon;
      if (v.lon > maxLon) maxLon = v.lon;
      if (v.lat < minLat) minLat = v.lat;
      if (v.lat > maxLat) maxLat = v.lat;
      count++;
    }
    return count === 0 ? null : [minLon, minLat, maxLon, maxLat];
  }
}

function indexVehicles(vehicles: Vehicle[]): Map<string, Vehicle> {
  const m = new Map<string, Vehicle>();
  for (const v of vehicles) m.set(v.id, v);
  return m;
}

function clamp(x: number, lo: number, hi: number): number {
  return x < lo ? lo : x > hi ? hi : x;
}
