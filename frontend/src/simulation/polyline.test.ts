import { describe, expect, it } from 'vitest';
import {
  cumulativeDistances,
  interpolateAlongPolyline,
  pointAtArcLength,
  snapToPolyline,
  SNAP_THRESHOLD_M,
} from './polyline';
import type { LonLat } from './polyline';

describe('cumulativeDistances', () => {
  it('returns empty array for empty polyline', () => {
    expect(cumulativeDistances([])).toEqual([]);
  });

  it('returns [0] for single-point polyline', () => {
    expect(cumulativeDistances([[29.0, 41.0]])).toEqual([0]);
  });

  it('returns [0, d] for two-point polyline (~1.11 km for 0.01 deg latitude)', () => {
    const cum = cumulativeDistances([
      [29.0, 41.0],
      [29.0, 41.01],
    ]);
    expect(cum).toHaveLength(2);
    expect(cum[0]).toBe(0);
    expect(cum[1]).toBeCloseTo(1112.0, 0);
  });

  it('is strictly monotonically increasing for a multi-point polyline', () => {
    const cum = cumulativeDistances([
      [29.0, 41.0],
      [29.005, 41.005],
      [29.01, 41.01],
      [29.015, 41.0],
    ]);
    for (let i = 1; i < cum.length; i++) {
      expect(cum[i]).toBeGreaterThan(cum[i - 1]);
    }
  });
});

describe('snapToPolyline', () => {
  it('snaps a point lying on the polyline back to itself', () => {
    const pl: LonLat[] = [
      [29.0, 41.0],
      [29.0, 41.01],
      [29.01, 41.01],
    ];
    const cum = cumulativeDistances(pl);
    const snap = snapToPolyline([29.0, 41.01], pl, cum);
    expect(snap).not.toBeNull();
    expect(snap!.distFromPoint).toBeLessThan(1);
    expect(snap!.arcLength).toBeCloseTo(cum[1], 0);
  });

  it('projects a near off-polyline point onto the closest segment', () => {
    const pl: LonLat[] = [
      [29.0, 41.0],
      [29.0, 41.01],
    ];
    const cum = cumulativeDistances(pl);
    const snap = snapToPolyline([29.001, 41.005], pl, cum);
    expect(snap).not.toBeNull();
    expect(snap!.segIdx).toBe(0);
    expect(snap!.t).toBeCloseTo(0.5, 2);
    expect(snap!.distFromPoint).toBeGreaterThan(0);
    expect(snap!.distFromPoint).toBeLessThan(SNAP_THRESHOLD_M);
  });

  it('returns null when the nearest projection exceeds SNAP_THRESHOLD_M', () => {
    const pl: LonLat[] = [
      [29.0, 41.0],
      [29.0, 41.01],
    ];
    const cum = cumulativeDistances(pl);
    expect(snapToPolyline([30.0, 42.0], pl, cum)).toBeNull();
  });
});

describe('pointAtArcLength', () => {
  const pl: LonLat[] = [
    [29.0, 41.0],
    [29.0, 41.01],
    [29.01, 41.01],
  ];
  const cum = cumulativeDistances(pl);
  const total = cum[cum.length - 1];

  it('returns the first vertex at s=0', () => {
    const pt = pointAtArcLength(0, pl, cum);
    expect(pt.lon).toBeCloseTo(29.0, 6);
    expect(pt.lat).toBeCloseTo(41.0, 6);
  });

  it('returns the last vertex at s=totalLength', () => {
    const pt = pointAtArcLength(total, pl, cum);
    expect(pt.lon).toBeCloseTo(29.01, 6);
    expect(pt.lat).toBeCloseTo(41.01, 6);
  });

  it('linearly interpolates within a segment for an arc-length in the middle', () => {
    const sMid = cum[1] / 2;
    const pt = pointAtArcLength(sMid, pl, cum);
    expect(pt.lon).toBeCloseTo(29.0, 6);
    expect(pt.lat).toBeCloseTo(41.005, 6);
  });
});

describe('interpolateAlongPolyline', () => {
  it('returns the arc-length midpoint, not the chord midpoint, on a curved polyline', () => {
    const pl: LonLat[] = [
      [29.0, 41.0],
      [29.0, 41.01],
      [29.01, 41.01],
      [29.01, 41.0],
    ];
    const result = interpolateAlongPolyline(pl[0], pl[3], pl, 0.5);
    expect(result).not.toBeNull();
    expect(result!.lon).toBeCloseTo(29.005, 4);
    expect(result!.lat).toBeCloseTo(41.01, 4);
    expect(Math.abs(result!.lat - 41.0)).toBeGreaterThan(0.005);
  });
});
