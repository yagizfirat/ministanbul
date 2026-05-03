import { describe, expect, it } from 'vitest';
import { computeNextStops, formatEta, formatTime } from './next_stops';
import type { PreparedTrip } from './scheduled_trip';

function prep(projections: { sec: number; name: string; seq: number }[]): PreparedTrip {
  return {
    trip_id: 't1',
    route_id: 'public:m2',
    short_name: 'M2',
    direction_id: 0,
    mode: 'metro',
    polyline: [[29.0, 41.0], [29.0, 41.01]],
    cumDist: [0, 1110],
    stopProjections: projections.map((p) => ({
      arrivalSec: p.sec,
      arcLengthM: 0,
      stopName: p.name,
      sequence: p.seq,
    })),
    firstArrSec: projections[0]?.sec ?? 0,
    lastArrSec: projections[projections.length - 1]?.sec ?? 0,
  };
}

describe('computeNextStops', () => {
  it('returns up to 5 future stops in arrivalSec order', () => {
    const p = prep([
      { sec: 36000, name: 'A', seq: 1 },
      { sec: 36060, name: 'B', seq: 2 },
      { sec: 36120, name: 'C', seq: 3 },
      { sec: 36180, name: 'D', seq: 4 },
      { sec: 36240, name: 'E', seq: 5 },
      { sec: 36300, name: 'F', seq: 6 },
      { sec: 36360, name: 'G', seq: 7 },
    ]);
    // Vehicle son 'A' durağına ulaşmış; 'B'...'F' sonraki 5 durak.
    const out = computeNextStops(p, 36000, 5);
    expect(out.map((s) => s.stopName)).toEqual(['B', 'C', 'D', 'E', 'F']);
    expect(out.map((s) => s.sequence)).toEqual([2, 3, 4, 5, 6]);
  });

  it('filters out past arrivals (<= nowSec)', () => {
    const p = prep([
      { sec: 36000, name: 'past', seq: 1 },
      { sec: 36060, name: 'now-equal', seq: 2 },
      { sec: 36120, name: 'next', seq: 3 },
    ]);
    // arrivalSec === nowSec geçmiş sayılır (vehicle durakta veya geçmiş).
    const out = computeNextStops(p, 36060, 5);
    expect(out.map((s) => s.stopName)).toEqual(['next']);
  });

  it('returns empty when vehicle is past all stops (terminus)', () => {
    const p = prep([
      { sec: 36000, name: 'A', seq: 1 },
      { sec: 36060, name: 'B', seq: 2 },
    ]);
    expect(computeNextStops(p, 99999, 5)).toEqual([]);
  });

  it('returns empty when projections list is empty', () => {
    const p = prep([{ sec: 36000, name: 'A', seq: 1 }]);
    p.stopProjections = [];
    expect(computeNextStops(p, 36000, 5)).toEqual([]);
  });

  it('respects custom limit', () => {
    const p = prep([
      { sec: 36000, name: 'A', seq: 1 },
      { sec: 36060, name: 'B', seq: 2 },
      { sec: 36120, name: 'C', seq: 3 },
      { sec: 36180, name: 'D', seq: 4 },
    ]);
    expect(computeNextStops(p, 35999, 2).map((s) => s.stopName)).toEqual(['A', 'B']);
  });

  it('computes etaSeconds = arrivalSec - nowSec', () => {
    const p = prep([{ sec: 36120, name: 'X', seq: 1 }]);
    const [s] = computeNextStops(p, 36000, 5);
    expect(s.etaSeconds).toBe(120);
  });

  it('emits HH:MM scheduled string from arrivalSec', () => {
    // 14:32 = 14*3600 + 32*60 = 52320
    const p = prep([{ sec: 52320, name: 'X', seq: 1 }]);
    const [s] = computeNextStops(p, 50000, 5);
    expect(s.scheduled).toBe('14:32');
  });
});

describe('formatTime', () => {
  it('formats midnight + N seconds as HH:MM', () => {
    expect(formatTime(0)).toBe('00:00');
    expect(formatTime(60)).toBe('00:01');
    expect(formatTime(3600)).toBe('01:00');
    expect(formatTime(52320)).toBe('14:32');
  });

  it('wraps 24h overflow (overnight service 25:30 → 01:30)', () => {
    // 25:30 IST = 25*3600 + 30*60 = 91800
    expect(formatTime(91800)).toBe('01:30');
  });
});

describe('formatEta', () => {
  it('shows seconds under 1 minute', () => {
    expect(formatEta(0)).toBe('0sn');
    expect(formatEta(45)).toBe('45sn');
  });

  it('rounds to whole minutes between 1 min and 1 hour', () => {
    expect(formatEta(60)).toBe('1 dk');
    expect(formatEta(120)).toBe('2 dk');
    expect(formatEta(90)).toBe('2 dk');     // round up at .5
    expect(formatEta(3540)).toBe('59 dk');
  });

  it('shows hours + minutes for 1+ hour', () => {
    expect(formatEta(3600)).toBe('1 sa');
    expect(formatEta(3900)).toBe('1 sa 5 dk');
    expect(formatEta(7320)).toBe('2 sa 2 dk');
  });
});
