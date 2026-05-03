import { describe, expect, it } from 'vitest';
import { SnapshotStore } from './snapshot_store';
import type { VehicleSnapshot } from '../data/websocket';

// Test snapshot factory — VehicleSnapshot data/websocket'tan import
// edilirdi normalde, ama burada yapısı yeterince basit, inline.
// KM5-a (v0.8.0): mapped_count payload field'ı kaldırıldı (Spec §5.7).
interface MockSnapshot {
  timestamp: string;
  vehicle_count: number;
  vehicles: Array<{ id: string; lat: number; lon: number; bearing: number | null; speed: number; route_id: string | null }>;
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
