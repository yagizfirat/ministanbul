import { describe, expect, it } from 'vitest';
import { interpolateScheduledTrip, prepareTrip } from './scheduled_trip';
import type { ActiveTrip } from '../data/api';
import type { LonLat } from './polyline';

// Polyline with intentionally uneven segment lengths so trip-level lerp
// disagrees with stop-level lerp:
//   v0 [29.00, 41.00]
//   v1 [29.001, 41.000] — 0.001° east → ~84m  (very short)
//   v2 [29.001, 41.020] — 0.020° north → ~2225m (very long)
const SHAPE: LonLat[] = [
  [29.0, 41.0],
  [29.001, 41.0],
  [29.001, 41.02],
];

function makeTrip(overrides: Partial<ActiveTrip> = {}): ActiveTrip {
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
      { stop_id: 's0', stop_name: 'Stop 0', sequence: 1, arrival_seconds: 36000, lat: 41.0, lon: 29.0 },
      { stop_id: 's1', stop_name: 'Stop 1', sequence: 2, arrival_seconds: 36060, lat: 41.0, lon: 29.001 },
      { stop_id: 's2', stop_name: 'Stop 2', sequence: 3, arrival_seconds: 36300, lat: 41.02, lon: 29.001 },
    ],
    ...overrides,
  };
}

describe('prepareTrip', () => {
  it('builds a PreparedTrip with monotone arrivals + arc-lengths', () => {
    const prep = prepareTrip(makeTrip(), SHAPE);
    expect(prep).not.toBeNull();
    const p = prep!;
    expect(p.stopProjections).toHaveLength(3);
    const arrivals = p.stopProjections.map((sp) => sp.arrivalSec);
    expect(arrivals).toEqual([36000, 36060, 36300]);
    const arcs = p.stopProjections.map((sp) => sp.arcLengthM);
    for (let i = 1; i < arcs.length; i++) expect(arcs[i]).toBeGreaterThan(arcs[i - 1]);
    expect(p.firstArrSec).toBe(36000);
    expect(p.lastArrSec).toBe(36300);
  });

  it('does not reverse the polyline for direction_id=1 (backend already serves per-direction shape)', () => {
    const prepFwd = prepareTrip(makeTrip({ direction_id: 0 }), SHAPE)!;
    const prepRev = prepareTrip(makeTrip({ direction_id: 1 }), SHAPE)!;
    // Same incoming shape → identical working polyline regardless of direction_id.
    expect(prepFwd.polyline).toEqual(prepRev.polyline);
    expect(prepFwd.polyline[0]).toEqual(SHAPE[0]);
    expect(prepFwd.polyline[prepFwd.polyline.length - 1]).toEqual(SHAPE[SHAPE.length - 1]);
  });

  it('returns null when a stop is too far from the polyline (>500 m)', () => {
    const bad = makeTrip({
      stop_times: [
        { stop_id: 's0', stop_name: 'Stop 0', sequence: 1, arrival_seconds: 36000, lat: 41.0, lon: 29.0 },
        // 1° east of the polyline → ~84 km, far beyond SNAP_THRESHOLD_M
        { stop_id: 'far', stop_name: 'Far', sequence: 2, arrival_seconds: 36060, lat: 41.0, lon: 30.0 },
        { stop_id: 's2', stop_name: 'Stop 2', sequence: 3, arrival_seconds: 36300, lat: 41.02, lon: 29.001 },
      ],
    });
    expect(prepareTrip(bad, SHAPE)).toBeNull();
  });

  it('returns null when stop_times has fewer than 2 entries', () => {
    const tiny = makeTrip({
      stop_times: [
        { stop_id: 's0', stop_name: 'Stop 0', sequence: 1, arrival_seconds: 36000, lat: 41.0, lon: 29.0 },
      ],
    });
    expect(prepareTrip(tiny, SHAPE)).toBeNull();
  });
});

describe('interpolateScheduledTrip', () => {
  it('returns null before the first arrival', () => {
    const prep = prepareTrip(makeTrip(), SHAPE)!;
    expect(interpolateScheduledTrip(prep, 35999)).toBeNull();
  });

  it('returns null after the last arrival', () => {
    const prep = prepareTrip(makeTrip(), SHAPE)!;
    expect(interpolateScheduledTrip(prep, 36301)).toBeNull();
  });

  it('emits the first stop pose at firstArrSec', () => {
    const prep = prepareTrip(makeTrip(), SHAPE)!;
    const pose = interpolateScheduledTrip(prep, 36000)!;
    expect(pose).not.toBeNull();
    expect(pose.lat).toBeCloseTo(41.0, 5);
    expect(pose.lon).toBeCloseTo(29.0, 5);
    expect(pose.mode).toBe('metro');
  });

  it('emits the last stop pose at lastArrSec', () => {
    const prep = prepareTrip(makeTrip(), SHAPE)!;
    const pose = interpolateScheduledTrip(prep, 36300)!;
    expect(pose.lat).toBeCloseTo(41.02, 5);
    expect(pose.lon).toBeCloseTo(29.001, 5);
  });

  it('uses stop-level interpolation, not trip-level (uneven segments)', () => {
    // At the tripwide midpoint (36150) the trip-level lerp would put us at
    // 50% of the total arc-length (~1154m, near lat 41.01). But the *stop*
    // schedule says we just left s1 at 36060 and should reach s2 at 36300:
    //   t = (36150 - 36060) / (36300 - 36060) = 90/240 = 0.375
    //   between s1 (29.001, 41.000) and s2 (29.001, 41.020)
    //   → expected lat ≈ 41.0075, far below 41.01.
    const prep = prepareTrip(makeTrip(), SHAPE)!;
    const pose = interpolateScheduledTrip(prep, 36150)!;
    expect(pose.lon).toBeCloseTo(29.001, 5);
    expect(pose.lat).toBeCloseTo(41.0075, 3);
    expect(pose.lat).toBeLessThan(41.01); // sanity vs trip-level midpoint
  });
});
