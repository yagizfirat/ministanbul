import { describe, expect, it } from 'vitest';
import { ScheduledFleet } from './scheduled_fleet';
import type { ActiveTrip } from '../data/api';
import type { LonLat } from './polyline';

const SHAPE: LonLat[] = [
  [29.0, 41.0],
  [29.001, 41.0],
  [29.001, 41.02],
];

const SHAPE2: LonLat[] = [
  [29.1, 41.1],
  [29.105, 41.1],
];

function lookup(id: string): LonLat[] | null {
  if (id === 'sh1') return SHAPE;
  if (id === 'sh2') return SHAPE2;
  return null;
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
      { stop_id: 's0', sequence: 1, arrival_seconds: 36000, lat: 41.0, lon: 29.0 },
      { stop_id: 's1', sequence: 2, arrival_seconds: 36060, lat: 41.0, lon: 29.001 },
      { stop_id: 's2', sequence: 3, arrival_seconds: 36300, lat: 41.02, lon: 29.001 },
    ],
    ...overrides,
  };
}

describe('ScheduledFleet.setActiveTrips', () => {
  it('adds new trips and reports counts', () => {
    const fleet = new ScheduledFleet();
    const result = fleet.setActiveTrips([trip({}), trip({ trip_id: 't2' })], lookup);
    expect(result.added).toBe(2);
    expect(result.retained).toBe(0);
    expect(result.removed).toBe(0);
    expect(fleet.size()).toBe(2);
  });

  it('skips trips whose shape_id is not cached', () => {
    const fleet = new ScheduledFleet();
    const result = fleet.setActiveTrips(
      [trip({ trip_id: 'tx', shape_id: 'unknown' })],
      lookup,
    );
    expect(result.added).toBe(0);
    expect(result.skippedNoShape).toBe(1);
    expect(fleet.size()).toBe(0);
  });

  it('removes trips that drop out of the next poll', () => {
    const fleet = new ScheduledFleet();
    fleet.setActiveTrips([trip({}), trip({ trip_id: 't2' })], lookup);
    const second = fleet.setActiveTrips([trip({})], lookup);
    expect(second.added).toBe(0);
    expect(second.retained).toBe(1);
    expect(second.removed).toBe(1);
    expect(fleet.size()).toBe(1);
  });

  it('counts snap failures separately from no-shape', () => {
    const fleet = new ScheduledFleet();
    const bad = trip({
      trip_id: 'tbad',
      stop_times: [
        { stop_id: 's0', sequence: 1, arrival_seconds: 36000, lat: 41.0, lon: 29.0 },
        { stop_id: 'far', sequence: 2, arrival_seconds: 36300, lat: 41.0, lon: 30.0 },
      ],
    });
    const result = fleet.setActiveTrips([bad], lookup);
    expect(result.skippedSnapFail).toBe(1);
    expect(result.added).toBe(0);
  });
});

describe('ScheduledFleet.getInterpolated', () => {
  it('returns only trips whose window covers nowSec', () => {
    const fleet = new ScheduledFleet();
    fleet.setActiveTrips(
      [
        trip({ trip_id: 'now' }), // 36000-36300
        trip({
          trip_id: 'past',
          stop_times: [
            { stop_id: 's0', sequence: 1, arrival_seconds: 30000, lat: 41.0, lon: 29.0 },
            { stop_id: 's1', sequence: 2, arrival_seconds: 30100, lat: 41.0, lon: 29.001 },
            { stop_id: 's2', sequence: 3, arrival_seconds: 30200, lat: 41.02, lon: 29.001 },
          ],
        }),
      ],
      lookup,
    );
    const out = fleet.getInterpolated(36100);
    expect(out).toHaveLength(1);
    expect(out[0].trip_id).toBe('now');
  });

  it('returns empty when no trip is in window', () => {
    const fleet = new ScheduledFleet();
    fleet.setActiveTrips([trip({})], lookup);
    expect(fleet.getInterpolated(0)).toEqual([]);
  });
});
