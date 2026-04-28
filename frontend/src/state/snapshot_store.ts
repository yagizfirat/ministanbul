import { interpolatePosition } from '../simulation/interpolator';
import type { VehicleSnapshot } from '../data/websocket';

export interface Vehicle {
  id: string;
  lat: number;
  lon: number;
  bearing: number | null;
  speed: number;
  route_id: string | null;
}

export interface InterpolatedVehicle {
  id: string;
  lat: number;
  lon: number;
  route_id: string | null;
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
      out.push({ id, lat: pos.lat, lon: pos.lon, route_id: t1Vehicle.route_id });
    }
    return out;
  }

  latestTimestamp(): number | null {
    return this.t1?.dataTime ?? null;
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
