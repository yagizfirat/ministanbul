import { describe, expect, it } from 'vitest';
import type { Map as MapLibreMap } from 'maplibre-gl';
import {
  addRouteToMap,
  buildRouteFeature,
  buildRouteLineGlowPaint,
  buildRouteLinePaint,
  getRouteBBox,
  getRoutesBBox,
  removeRouteFromMap,
} from './route_lines_layer';
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

  it('focused null returns base paint (line-opacity sabit 0.85)', () => {
    expect(buildRouteLinePaint(null)['line-opacity']).toBe(0.85);
  });

  it('focused single id → line-opacity case ["in" literal] expression', () => {
    const p = buildRouteLinePaint(['public:m2']);
    const op = p['line-opacity'] as readonly unknown[];
    expect(op[0]).toBe('case');
    expect(op[1]).toEqual(['in', ['get', 'route_id'], ['literal', ['public:m2']]]);
    expect(op[2]).toBe(1.0);
    expect(op[3]).toBe(0.2);
  });

  it('focused multi-id (variant group) → "in" literal contains all ids', () => {
    const p = buildRouteLinePaint(['iett:1562', 'iett:1564', 'iett:1567']);
    const op = p['line-opacity'] as readonly unknown[];
    const literal = (op[1] as readonly unknown[])[2] as readonly unknown[];
    expect(literal[1]).toEqual(['iett:1562', 'iett:1564', 'iett:1567']);
  });

  it('focused empty array → base paint (no focus)', () => {
    expect(buildRouteLinePaint([])['line-opacity']).toBe(0.85);
  });

  it('focused dolu → line-width also case-driven (focused thicker)', () => {
    const w = buildRouteLinePaint(['public:m2'])['line-width'] as readonly unknown[];
    expect(w[0]).toBe('case');
  });
});

describe('buildRouteLineGlowPaint', () => {
  it('uses line-blur and a fat zoom-driven width (halo)', () => {
    const p = buildRouteLineGlowPaint();
    expect(p['line-blur']).toBe(4);
    expect(p['line-color']).toEqual(['get', 'color']);
    expect(p['line-opacity']).toBe(0.4);
    const w = p['line-width'] as readonly unknown[];
    expect(w[0]).toBe('interpolate');
  });
});

describe('getRoutesBBox (f-polish-5 — union over variant group)', () => {
  const stubMap = { getSource: () => undefined } as unknown as MapLibreMap;

  it('returns null for empty input', () => {
    expect(getRoutesBBox([])).toBeNull();
  });

  it('union bbox over multiple routes covers all coords', () => {
    addRouteToMap(stubMap, 'r1', 'metro', 'A', '#000', {
      type: 'Feature',
      geometry: {
        type: 'LineString',
        coordinates: [[29.0, 41.0], [29.05, 41.05]] as [number, number][],
      },
      properties: { shape_id: 's-r1' },
    });
    addRouteToMap(stubMap, 'r2', 'metro', 'A', '#000', {
      type: 'Feature',
      geometry: {
        type: 'LineString',
        coordinates: [[28.95, 41.10], [29.10, 41.15]] as [number, number][],
      },
      properties: { shape_id: 's-r2' },
    });
    expect(getRoutesBBox(['r1', 'r2'])).toEqual([28.95, 41.0, 29.10, 41.15]);
    removeRouteFromMap(stubMap, 'r1');
    removeRouteFromMap(stubMap, 'r2');
  });
});

describe('getRouteBBox', () => {
  // Stub map — addRouteToMap'in flush() çağrısında getSource undefined
  // döner, setData no-op. Module-level collection sadece feature push'tan
  // etkilenir.
  const stubMap = {
    getSource: () => undefined,
  } as unknown as MapLibreMap;

  it('returns null for an unknown route', () => {
    expect(getRouteBBox('public:nope')).toBeNull();
  });

  it('computes min/max lon-lat across the geometry coordinates', () => {
    const shape = {
      type: 'Feature' as const,
      geometry: {
        type: 'LineString' as const,
        coordinates: [
          [29.0, 41.0],
          [29.05, 41.10],
          [28.95, 41.05],
        ] as [number, number][],
      },
      properties: { shape_id: 'sh-bbox' },
    };
    addRouteToMap(stubMap, 'public:bbox-test', 'metro', 'M-X', '#000000', shape);
    const bbox = getRouteBBox('public:bbox-test');
    expect(bbox).toEqual([28.95, 41.0, 29.05, 41.1]);
    removeRouteFromMap(stubMap, 'public:bbox-test'); // cleanup
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
