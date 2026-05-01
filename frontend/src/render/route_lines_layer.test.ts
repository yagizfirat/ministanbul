import { describe, expect, it } from 'vitest';
import { buildRouteLinePaint, buildRouteFeature } from './route_lines_layer';
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
