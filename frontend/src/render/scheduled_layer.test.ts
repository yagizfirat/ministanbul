import { describe, expect, it } from 'vitest';
import { buildScheduledLayerPaint, buildScheduledFeature } from './scheduled_layer';
import {
  ROUTE_COLORS,
  MODE_FALLBACK_COLORS,
  lighten,
} from '../styling/route_colors';
import type { InterpolatedScheduledTrip } from '../simulation/scheduled_trip';

describe('buildScheduledLayerPaint', () => {
  it('binds circle-color to per-feature color (data-driven)', () => {
    expect(buildScheduledLayerPaint()['circle-color']).toEqual(['get', 'color']);
  });

  it('binds circle-stroke-color to per-feature strokeColor (data-driven)', () => {
    expect(buildScheduledLayerPaint()['circle-stroke-color']).toEqual(['get', 'strokeColor']);
  });

  it('keeps a non-zero stroke width and zoom-driven radius', () => {
    const paint = buildScheduledLayerPaint();
    expect(paint['circle-stroke-width']).toBeGreaterThan(0);
    expect(Array.isArray(paint['circle-radius'])).toBe(true);
    expect(paint['circle-radius'][0]).toBe('interpolate');
  });
});

function pose(
  short_name: string,
  mode: string,
  route_id = `public:${short_name.toLowerCase()}`,
): InterpolatedScheduledTrip {
  return {
    trip_id: `t-${short_name}`,
    route_id,
    short_name,
    lon: 29.0,
    lat: 41.0,
    bearing: 0,
    mode,
  };
}

describe('buildScheduledFeature — corporate-color injection', () => {
  it('M2 (metro): fill = lighten green, stroke = green', () => {
    const f = buildScheduledFeature(pose('M2', 'metro'));
    expect(f.properties.strokeColor).toBe(ROUTE_COLORS.M2);
    expect(f.properties.color).toBe(lighten(ROUTE_COLORS.M2, 0.2));
  });

  it('M1A (metro): fill = lighten red, stroke = red', () => {
    const f = buildScheduledFeature(pose('M1A', 'metro'));
    expect(f.properties.strokeColor).toBe(ROUTE_COLORS.M1A);
    expect(f.properties.color).toBe(lighten(ROUTE_COLORS.M1A, 0.2));
  });

  it('T1 (tram): fill = lighten navy, stroke = navy', () => {
    const f = buildScheduledFeature(pose('T1', 'tram'));
    expect(f.properties.strokeColor).toBe(ROUTE_COLORS.T1);
    expect(f.properties.color).toBe(lighten(ROUTE_COLORS.T1, 0.2));
  });

  it('F1 (funicular): falls back to mode color, fill = lighten orange', () => {
    const f = buildScheduledFeature(pose('F1', 'funicular'));
    expect(f.properties.strokeColor).toBe(MODE_FALLBACK_COLORS.funicular);
    expect(f.properties.color).toBe(lighten(MODE_FALLBACK_COLORS.funicular, 0.2));
  });

  it('lightened fill is distinct from the base stroke (sanity)', () => {
    const f = buildScheduledFeature(pose('M2', 'metro'));
    expect(f.properties.color).not.toBe(f.properties.strokeColor);
    expect(f.properties.color).toMatch(/^#[0-9A-F]{6}$/);
  });

  it('carries trip_id and mode to the feature properties', () => {
    const p = pose('M2', 'metro');
    const f = buildScheduledFeature(p);
    expect(f.properties.trip_id).toBe(p.trip_id);
    expect(f.properties.mode).toBe(p.mode);
  });

  it('places the geometry at the pose lon/lat', () => {
    const f = buildScheduledFeature(pose('M2', 'metro'));
    expect(f.geometry.coordinates).toEqual([29.0, 41.0]);
  });

  it('propagates route_id into properties (KM1 alt-iş f-6)', () => {
    const f = buildScheduledFeature(pose('M2', 'metro', 'public:1298'));
    expect(f.properties.route_id).toBe('public:1298');
  });
});
