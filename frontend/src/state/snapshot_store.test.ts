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
