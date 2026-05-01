import { describe, expect, it } from 'vitest';
import { buildFleetPaint } from './fleet_layer';
import { MODE_FALLBACK_COLORS } from '../styling/route_colors';

describe('buildFleetPaint', () => {
  it('returns a circle paint spec with all required keys', () => {
    const paint = buildFleetPaint();
    expect(paint['circle-radius']).toBeTruthy();
    expect(paint['circle-color']).toBeTruthy();
    expect(paint['circle-stroke-width']).toBeDefined();
    expect(paint['circle-stroke-color']).toBeTruthy();
  });

  it('uses İBB municipal yellow as the fill for every IETT vehicle', () => {
    expect(buildFleetPaint()['circle-color']).toBe(MODE_FALLBACK_COLORS.bus);
  });

  it('drives circle-stroke-width via a case on ["has","route_id"]', () => {
    const w = buildFleetPaint()['circle-stroke-width'];
    expect(Array.isArray(w)).toBe(true);
    expect(w[0]).toBe('case');
    // [case, condition, then, else]
    expect(w[1]).toEqual(['has', 'route_id']);
    expect(w[2]).toBeGreaterThan(0); // mapped → visible border
    expect(w[3]).toBe(0);            // unmapped → no border
  });

  it('uses an interpolate expression for circle-radius (zoom-driven)', () => {
    const radius = buildFleetPaint()['circle-radius'];
    expect(Array.isArray(radius)).toBe(true);
    expect(radius[0]).toBe('interpolate');
  });

  it('focused null → no circle-opacity (default rendering)', () => {
    expect((buildFleetPaint(null) as Record<string, unknown>)['circle-opacity']).toBeUndefined();
  });

  it('focused dolu → circle-opacity case expression', () => {
    const paint = buildFleetPaint('iett:29B') as Record<string, unknown>;
    const op = paint['circle-opacity'] as readonly unknown[];
    expect(op[0]).toBe('case');
    expect(op[2]).toBe(1.0);
    expect(op[3]).toBe(0.2);
  });

  it('manually evaluates the stroke-width case for a mapped vs unmapped feature', () => {
    // Tiny inline evaluator to prove the expression's intent end-to-end.
    const expr = buildFleetPaint()['circle-stroke-width'] as readonly [
      'case',
      readonly ['has', string],
      number,
      number,
    ];
    const ev = (props: Record<string, unknown>): number => {
      const [, cond, thenV, elseV] = expr;
      return cond[0] === 'has' && cond[1] in props ? thenV : elseV;
    };
    expect(ev({ id: 'x', route_id: '34A' })).toBe(1.5);
    expect(ev({ id: 'x' })).toBe(0);
  });
});
