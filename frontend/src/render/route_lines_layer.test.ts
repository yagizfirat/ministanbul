import { describe, expect, it } from 'vitest';
import { buildRouteLinePaint, buildRouteFeature } from './route_lines_layer';
import { getRouteColor, ROUTE_COLORS, MODE_FALLBACK_COLORS } from '../styling/route_colors';
import type { ShapeFeature } from '../data/api';

describe('buildRouteLinePaint', () => {
  it('binds line-color to the per-feature color property', () => {
    expect(buildRouteLinePaint()['line-color']).toEqual(['get', 'color']);
  });

  it('returns a paint spec with all required keys', () => {
    const paint = buildRouteLinePaint();
    expect(paint['line-color']).toBeTruthy();
    expect(paint['line-opacity']).toBe(0.85);
    expect(paint['line-width']).toBeTruthy();
  });

  it('uses an interpolate expression for line-width (zoom-driven)', () => {
    const w = buildRouteLinePaint()['line-width'];
    expect(Array.isArray(w)).toBe(true);
    expect(w[0]).toBe('interpolate');
  });
});

const SHAPE: ShapeFeature = {
  type: 'Feature',
  geometry: {
    type: 'LineString',
    coordinates: [
      [29.0, 41.0],
      [29.01, 41.01],
    ],
  },
  properties: { shape_id: '2476' },
};

describe('buildRouteFeature', () => {
  it('produces a Feature whose properties carry route_id, shape_id, short_name, mode, color', () => {
    const f = buildRouteFeature('public:1298', 'M2', 'metro', '#059A4D', SHAPE);
    expect(f.type).toBe('Feature');
    expect(f.geometry).toBe(SHAPE.geometry);
    expect(f.properties).toEqual({
      route_id: 'public:1298',
      shape_id: '2476',
      short_name: 'M2',
      mode: 'metro',
      color: '#059A4D',
    });
  });

  it('keeps the color exactly as passed in (no internal lookup)', () => {
    // Pure function contract: color hesaplaması route_store'da yapılır,
    // bu modül sadece feature'a yapıştırır.
    const f = buildRouteFeature('r1', 'X', 'metro', '#ABCDEF', SHAPE);
    expect(f.properties.color).toBe('#ABCDEF');
  });
});

describe('route_store integration: getRouteColor → buildRouteFeature', () => {
  it('paints M2 with its corporate green', () => {
    const color = getRouteColor('M2', 'metro');
    const f = buildRouteFeature('public:1298', 'M2', 'metro', color, SHAPE);
    expect(f.properties.color).toBe(ROUTE_COLORS.M2); // '#059A4D'
  });

  it('paints M1A with corporate red', () => {
    const color = getRouteColor('M1A', 'metro');
    const f = buildRouteFeature('public:m1a', 'M1A', 'metro', color, SHAPE);
    expect(f.properties.color).toBe(ROUTE_COLORS.M1A); // '#EE2229'
  });

  it('paints T1 with corporate navy', () => {
    const color = getRouteColor('T1', 'tram');
    const f = buildRouteFeature('public:t1', 'T1', 'tram', color, SHAPE);
    expect(f.properties.color).toBe(ROUTE_COLORS.T1); // '#004B86'
  });

  it('falls back to mode color for an unknown funicular', () => {
    const color = getRouteColor('F1', 'funicular');
    const f = buildRouteFeature('public:f1', 'F1', 'funicular', color, SHAPE);
    expect(f.properties.color).toBe(MODE_FALLBACK_COLORS.funicular);
  });
});
