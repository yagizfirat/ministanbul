import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ScheduledFleet } from './scheduled_fleet';
import type { ActiveTrip } from '../data/api';
import type { LonLat } from './polyline';

const SHAPE_SH1: LonLat[] = [
  [29.0, 41.0],
  [29.001, 41.0],
  [29.001, 41.02],
];

const SHAPE_SH2: LonLat[] = [
  [29.1, 41.1],
  [29.105, 41.1],
];

function shapePayload(shapeId: string, coords: LonLat[]) {
  return {
    type: 'Feature',
    geometry: { type: 'LineString', coordinates: coords },
    properties: { shape_id: shapeId },
  };
}

function trip(overrides: Partial<ActiveTrip>): ActiveTrip {
  return {
    trip_id: 't1',
    route_id: 'public:m2',
    route_short_name: 'M2',
    route_long_name: 'A - B',
    shape_id: 'sh1',
    direction_id: 0,
    headsign: 'B',
    mode: 'metro',
    stop_times: [
      { stop_id: 's0', stop_name: 's0', sequence: 1, arrival_seconds: 36000, lat: 41.0, lon: 29.0 },
      { stop_id: 's1', stop_name: 's1', sequence: 2, arrival_seconds: 36060, lat: 41.0, lon: 29.001 },
      { stop_id: 's2', stop_name: 's2', sequence: 3, arrival_seconds: 36300, lat: 41.02, lon: 29.001 },
    ],
    ...overrides,
  };
}

function trip2(overrides: Partial<ActiveTrip>): ActiveTrip {
  return {
    ...trip({}),
    trip_id: 't2',
    shape_id: 'sh2',
    stop_times: [
      { stop_id: 'a', stop_name: 'a', sequence: 1, arrival_seconds: 40000, lat: 41.1, lon: 29.1 },
      { stop_id: 'b', stop_name: 'b', sequence: 2, arrival_seconds: 40060, lat: 41.1, lon: 29.105 },
    ],
    ...overrides,
  };
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn(async (url: string) => {
    if (url.includes('/api/shapes/sh1/')) {
      return { ok: true, json: async () => shapePayload('sh1', SHAPE_SH1) };
    }
    if (url.includes('/api/shapes/sh2/')) {
      return { ok: true, json: async () => shapePayload('sh2', SHAPE_SH2) };
    }
    return { ok: false, status: 404, json: async () => ({}) };
  });
  global.fetch = fetchMock as unknown as typeof fetch;
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('ScheduledFleet.setActiveTrips', () => {
  it('fetches shapes lazily and prepares trips', async () => {
    const fleet = new ScheduledFleet();
    const result = await fleet.setActiveTrips([trip({}), trip2({})]);
    expect(result.added).toBe(2);
    expect(result.removed).toBe(0);
    expect(fleet.size()).toBe(2);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('does not refetch a shape that is already cached', async () => {
    const fleet = new ScheduledFleet();
    await fleet.setActiveTrips([trip({})]);
    fetchMock.mockClear();
    // Second poll: same trip retained, plus a new trip on the SAME shape.
    await fleet.setActiveTrips([
      trip({}),
      trip({ trip_id: 't1b' }),
    ]);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('does not refetch a shape on a fresh poll if already cached', async () => {
    const fleet = new ScheduledFleet();
    await fleet.setActiveTrips([trip({})]);
    fetchMock.mockClear();
    // Trip dropped and re-added — shape already in cache, no HTTP needed.
    await fleet.setActiveTrips([]);
    await fleet.setActiveTrips([trip({})]);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('counts a missing shape (HTTP 404) as skippedNoShape', async () => {
    const fleet = new ScheduledFleet();
    const result = await fleet.setActiveTrips([
      trip({ trip_id: 'tx', shape_id: 'unknown' }),
    ]);
    expect(result.added).toBe(0);
    expect(result.skippedNoShape).toBe(1);
    expect(fleet.size()).toBe(0);
  });

  it('counts shape_id=null as skippedNoShape (no fetch attempted)', async () => {
    const fleet = new ScheduledFleet();
    fetchMock.mockClear();
    const result = await fleet.setActiveTrips([
      trip({ trip_id: 'tnull', shape_id: null }),
    ]);
    expect(result.skippedNoShape).toBe(1);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('removes trips that drop out of the next poll', async () => {
    const fleet = new ScheduledFleet();
    await fleet.setActiveTrips([trip({}), trip({ trip_id: 't_other' })]);
    const second = await fleet.setActiveTrips([trip({})]);
    expect(second.added).toBe(0);
    expect(second.retained).toBe(1);
    expect(second.removed).toBe(1);
    expect(fleet.size()).toBe(1);
  });

  it('counts snap failures separately from no-shape', async () => {
    const fleet = new ScheduledFleet();
    const bad = trip({
      trip_id: 'tbad',
      stop_times: [
        { stop_id: 's0', stop_name: 's0', sequence: 1, arrival_seconds: 36000, lat: 41.0, lon: 29.0 },
        // 1° east — far beyond SNAP_THRESHOLD_M
        { stop_id: 'far', stop_name: 'far', sequence: 2, arrival_seconds: 36300, lat: 41.0, lon: 30.0 },
      ],
    });
    const result = await fleet.setActiveTrips([bad]);
    expect(result.skippedSnapFail).toBe(1);
    expect(result.added).toBe(0);
  });
});

describe('ScheduledFleet — multi-instance isolation', () => {
  it('two fleets cache shapes independently', async () => {
    const metroFleet = new ScheduledFleet();
    const ferryFleet = new ScheduledFleet();
    await metroFleet.setActiveTrips([trip({})]); // shape sh1
    await ferryFleet.setActiveTrips([trip2({})]); // shape sh2
    expect(metroFleet.shapeCacheSize()).toBe(1);
    expect(ferryFleet.shapeCacheSize()).toBe(1);
    expect(metroFleet.size()).toBe(1);
    expect(ferryFleet.size()).toBe(1);
    // sh1 fetched once for metro, sh2 fetched once for ferry → 2 total.
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('removing a trip from one fleet does not touch the other', async () => {
    const metroFleet = new ScheduledFleet();
    const ferryFleet = new ScheduledFleet();
    await metroFleet.setActiveTrips([trip({})]);
    await ferryFleet.setActiveTrips([trip2({})]);
    await metroFleet.setActiveTrips([]);
    expect(metroFleet.size()).toBe(0);
    expect(ferryFleet.size()).toBe(1);
  });
});

describe('ScheduledFleet.getInterpolated', () => {
  it('returns only trips whose window covers nowSec', async () => {
    const fleet = new ScheduledFleet();
    await fleet.setActiveTrips([
      trip({ trip_id: 'now' }), // 36000-36300
      trip({
        trip_id: 'past',
        stop_times: [
          { stop_id: 's0', stop_name: 's0', sequence: 1, arrival_seconds: 30000, lat: 41.0, lon: 29.0 },
          { stop_id: 's1', stop_name: 's1', sequence: 2, arrival_seconds: 30100, lat: 41.0, lon: 29.001 },
          { stop_id: 's2', stop_name: 's2', sequence: 3, arrival_seconds: 30200, lat: 41.02, lon: 29.001 },
        ],
      }),
    ]);
    const out = fleet.getInterpolated(36100);
    expect(out).toHaveLength(1);
    expect(out[0].trip_id).toBe('now');
  });

  it('returns empty when no trip is in window', async () => {
    const fleet = new ScheduledFleet();
    await fleet.setActiveTrips([trip({})]);
    expect(fleet.getInterpolated(0)).toEqual([]);
  });
});

// KM-d.1 fix (Spec Ek A.19 borç #6): ferry için bbox fallback. Vapur
// route_lines_layer.collection'a eklenmiyor (KM3 paterni — denizüstü
// polyline anlamsız), SnapshotStore İETT canlı kapsamında. Aktif
// PreparedTrip'lerin polyline koordinatları tek kaynak.
describe('ScheduledFleet.getRouteBBox / getRoutesBBox (KM-d.1)', () => {
  it('returns null when no prepared trips exist', () => {
    const fleet = new ScheduledFleet();
    expect(fleet.getRouteBBox('public:m2')).toBeNull();
    expect(fleet.getRoutesBBox(['public:m2', 'public:f1'])).toBeNull();
  });

  it('returns null for empty routeIds array', async () => {
    const fleet = new ScheduledFleet();
    await fleet.setActiveTrips([trip({})]);
    expect(fleet.getRoutesBBox([])).toBeNull();
  });

  it('returns the polyline bbox of a single matching trip', async () => {
    const fleet = new ScheduledFleet();
    await fleet.setActiveTrips([trip({})]); // SHAPE_SH1 [[29.0,41.0],[29.001,41.0],[29.001,41.02]]
    const bbox = fleet.getRouteBBox('public:m2');
    expect(bbox).not.toBeNull();
    expect(bbox![0]).toBeCloseTo(29.0, 6);    // minLon
    expect(bbox![1]).toBeCloseTo(41.0, 6);    // minLat
    expect(bbox![2]).toBeCloseTo(29.001, 6);  // maxLon
    expect(bbox![3]).toBeCloseTo(41.02, 6);   // maxLat
  });

  it('returns null when route_id does not match any prepared trip', async () => {
    const fleet = new ScheduledFleet();
    await fleet.setActiveTrips([trip({})]);
    expect(fleet.getRouteBBox('public:nope')).toBeNull();
  });

  it('unions polyline coords across multiple matching trips (variant group)', async () => {
    const fleet = new ScheduledFleet();
    // İki trip aynı route_id, farklı shape — union polyline modlar +
    // ferry için variant grup bbox testi.
    await fleet.setActiveTrips([
      trip({ trip_id: 'a' }),                                  // SHAPE_SH1
      trip2({ route_id: 'public:m2', trip_id: 'b' }),          // SHAPE_SH2
    ]);
    const bbox = fleet.getRoutesBBox(['public:m2']);
    expect(bbox).not.toBeNull();
    // Union: SH1 [29.0..29.001, 41.0..41.02] + SH2 [29.1..29.105, 41.1..41.1]
    expect(bbox![0]).toBeCloseTo(29.0, 6);
    expect(bbox![1]).toBeCloseTo(41.0, 6);
    expect(bbox![2]).toBeCloseTo(29.105, 6);
    expect(bbox![3]).toBeCloseTo(41.1, 6);
  });

  it('isolates bbox to only matching route_ids (multi-route filter)', async () => {
    const fleet = new ScheduledFleet();
    await fleet.setActiveTrips([
      trip({ trip_id: 'a' }),                                  // route_id public:m2, SH1
      trip2({ route_id: 'public:f1', trip_id: 'b' }),          // route_id public:f1, SH2
    ]);
    // Only m2 → SH1 bbox
    const m2 = fleet.getRoutesBBox(['public:m2']);
    expect(m2).toEqual([29.0, 41.0, 29.001, 41.02]);
    // Only f1 → SH2 bbox
    const f1 = fleet.getRoutesBBox(['public:f1']);
    expect(f1).toEqual([29.1, 41.1, 29.105, 41.1]);
    // Both → union
    const both = fleet.getRoutesBBox(['public:m2', 'public:f1']);
    expect(both).toEqual([29.0, 41.0, 29.105, 41.1]);
  });
});
