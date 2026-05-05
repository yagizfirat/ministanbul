import { describe, expect, it } from 'vitest';
import { SnapshotStore } from './snapshot_store';
import type { VehicleSnapshot } from '../data/websocket';

// Test snapshot factory — VehicleSnapshot data/websocket'tan import
// edilirdi normalde, ama burada yapısı yeterince basit, inline.
// KM5-a (v0.8.0): mapped_count payload field'ı kaldırıldı (Spec §5.7).
interface MockSnapshot {
  timestamp: string;
  vehicle_count: number;
  vehicles: Array<{
    id: string;
    lat: number;
    lon: number;
    bearing: number | null;
    speed: number;
    route_id: string | null;
    is_metrobus?: boolean;
  }>;
}

function snap(vehicles: MockSnapshot['vehicles']): MockSnapshot {
  return {
    timestamp: new Date().toISOString(),
    vehicle_count: vehicles.length,
    vehicles,
  };
}

// ── v0.8.3 KM-b: getAlpha (frozen-state guard helper) ──────────────
describe('SnapshotStore.getAlpha', () => {
  it('returns null before any snapshot has been pushed', () => {
    const s = new SnapshotStore();
    expect(s.getAlpha(performance.now())).toBeNull();
  });

  it('returns alpha in [0, 1] after a single push (interval=0 → fallback denom)', () => {
    const s = new SnapshotStore();
    s.push(
      snap([{ id: 'v1', lat: 41, lon: 29, bearing: null, speed: 0, route_id: null }]) as unknown as VehicleSnapshot,
    );
    // push() ilk çağrıda t0=t1=next setler → t0/t1 dolu, interval=0 →
    // denom=FALLBACK_INTERVAL_MS. elapsed≈0 → alpha≈0.
    const a = s.getAlpha(performance.now());
    expect(a).not.toBeNull();
    expect(a! >= 0 && a! <= 1).toBe(true);
  });

  it('returns alpha clamped to [0, 1] across a synthetic interval', () => {
    const s = new SnapshotStore();
    s.push(
      snap([{ id: 'v1', lat: 41, lon: 29, bearing: null, speed: 0, route_id: null }]) as unknown as VehicleSnapshot,
    );
    s.push(
      snap([{ id: 'v1', lat: 41.1, lon: 29.1, bearing: null, speed: 0, route_id: null }]) as unknown as VehicleSnapshot,
    );
    const t1Wall = performance.now();
    expect(s.getAlpha(t1Wall)).toBeLessThan(0.05);
    expect(s.getAlpha(t1Wall + 10 * 60 * 1000)).toBe(1);
  });

  it('returns 1 in the frozen-state (way past the interval)', () => {
    const s = new SnapshotStore();
    s.push(
      snap([{ id: 'v1', lat: 41, lon: 29, bearing: null, speed: 0, route_id: null }]) as unknown as VehicleSnapshot,
    );
    s.push(
      snap([{ id: 'v1', lat: 42, lon: 30, bearing: null, speed: 0, route_id: null }]) as unknown as VehicleSnapshot,
    );
    // 5 dakika sonra → interval ≪ elapsed → clamp 1
    expect(s.getAlpha(performance.now() + 5 * 60 * 1000)).toBe(1);
  });
});

describe('SnapshotStore.getVehicleBBoxForRoute', () => {
  it('returns null when no snapshot has been pushed', () => {
    const s = new SnapshotStore();
    expect(s.getVehicleBBoxForRoute('iett:29B')).toBeNull();
  });

  it('returns null when no vehicle on the route is in the latest snapshot', () => {
    const s = new SnapshotStore();
    s.push(
      snap([
        { id: 'v1', lat: 41.0, lon: 29.0, bearing: null, speed: 0, route_id: 'iett:1' },
      ]) as unknown as VehicleSnapshot,
    );
    expect(s.getVehicleBBoxForRoute('iett:29B')).toBeNull();
  });

  it('computes min/max lon/lat over matching vehicles', () => {
    const s = new SnapshotStore();
    s.push(
      snap([
        { id: 'a', lat: 41.0, lon: 29.0, bearing: null, speed: 0, route_id: 'iett:29B' },
        { id: 'b', lat: 41.05, lon: 29.10, bearing: null, speed: 0, route_id: 'iett:29B' },
        { id: 'c', lat: 41.20, lon: 29.30, bearing: null, speed: 0, route_id: 'iett:29B' },
        // Hat dışı — dahil edilmemeli
        { id: 'd', lat: 40.5, lon: 28.5, bearing: null, speed: 0, route_id: 'iett:1' },
      ]) as unknown as VehicleSnapshot,
    );
    expect(s.getVehicleBBoxForRoute('iett:29B')).toEqual([29.0, 41.0, 29.30, 41.20]);
  });

  it('getVehicleBBoxForRoutes (multi) computes union over variant ids', () => {
    const s = new SnapshotStore();
    s.push(
      snap([
        { id: 'a', lat: 41.0, lon: 29.0, bearing: null, speed: 0, route_id: 'iett:1562' },
        { id: 'b', lat: 41.10, lon: 29.10, bearing: null, speed: 0, route_id: 'iett:1564' },
        { id: 'c', lat: 41.20, lon: 29.20, bearing: null, speed: 0, route_id: 'iett:1567' },
        // Group dışı — dahil edilmemeli
        { id: 'd', lat: 40.5, lon: 28.5, bearing: null, speed: 0, route_id: 'iett:other' },
      ]) as unknown as VehicleSnapshot,
    );
    expect(s.getVehicleBBoxForRoutes(['iett:1562', 'iett:1564', 'iett:1567']))
      .toEqual([29.0, 41.0, 29.20, 41.20]);
  });

  it('getVehicleBBoxForRoutes returns null for empty input', () => {
    const s = new SnapshotStore();
    s.push(snap([
      { id: 'a', lat: 41.0, lon: 29.0, bearing: null, speed: 0, route_id: 'iett:1' },
    ]) as unknown as VehicleSnapshot);
    expect(s.getVehicleBBoxForRoutes([])).toBeNull();
  });

  it('uses the latest snapshot only (t1), not t0', () => {
    const s = new SnapshotStore();
    s.push(
      snap([
        { id: 'old', lat: 40.0, lon: 28.0, bearing: null, speed: 0, route_id: 'iett:29B' },
      ]) as unknown as VehicleSnapshot,
    );
    s.push(
      snap([
        { id: 'new', lat: 41.0, lon: 29.0, bearing: null, speed: 0, route_id: 'iett:29B' },
      ]) as unknown as VehicleSnapshot,
    );
    const bbox = s.getVehicleBBoxForRoute('iett:29B');
    expect(bbox).toEqual([29.0, 41.0, 29.0, 41.0]);
  });
});

// KM5-e.2: backend is_metrobus payload field interpolation pipeline
// boyunca taşınır; fleet_layer paint expression bu field'ı okur.
describe('SnapshotStore.is_metrobus pass-through (KM5-e.2)', () => {
  it('forwards is_metrobus from snapshot to InterpolatedVehicle', () => {
    const s = new SnapshotStore();
    s.push(
      snap([
        { id: 'm1', lat: 41.0, lon: 29.0, bearing: null, speed: 0, route_id: null, is_metrobus: true },
        { id: 'b1', lat: 41.0, lon: 29.0, bearing: null, speed: 0, route_id: null, is_metrobus: false },
      ]) as unknown as VehicleSnapshot,
    );
    const out = s.getInterpolated(performance.now());
    const byId = new Map(out.map((v) => [v.id, v]));
    expect(byId.get('m1')?.is_metrobus).toBe(true);
    expect(byId.get('b1')?.is_metrobus).toBe(false);
  });

  it('countByMetrobus splits bus vs metrobus from latest snapshot', () => {
    const s = new SnapshotStore();
    s.push(
      snap([
        { id: '1', lat: 41, lon: 29, bearing: null, speed: 0, route_id: null, is_metrobus: true },
        { id: '2', lat: 41, lon: 29, bearing: null, speed: 0, route_id: null, is_metrobus: true },
        { id: '3', lat: 41, lon: 29, bearing: null, speed: 0, route_id: null, is_metrobus: false },
        { id: '4', lat: 41, lon: 29, bearing: null, speed: 0, route_id: null }, // missing → bus
      ]) as unknown as VehicleSnapshot,
    );
    expect(s.countByMetrobus()).toEqual({ bus: 2, metrobus: 2 });
  });

  it('countByMetrobus returns {0,0} when no snapshot has been pushed', () => {
    const s = new SnapshotStore();
    expect(s.countByMetrobus()).toEqual({ bus: 0, metrobus: 0 });
  });
});
