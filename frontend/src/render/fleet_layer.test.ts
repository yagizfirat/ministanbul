import { describe, expect, it } from 'vitest';
import { buildFleetFilter, buildFleetPaint } from './fleet_layer';
import { MODE_FALLBACK_COLORS } from '../styling/route_colors';

describe('buildFleetPaint', () => {
  it('returns a circle paint spec with all required keys', () => {
    const paint = buildFleetPaint();
    expect(paint['circle-radius']).toBeTruthy();
    expect(paint['circle-color']).toBeTruthy();
    expect(paint['circle-stroke-width']).toBeDefined();
    expect(paint['circle-stroke-color']).toBeTruthy();
  });

  // KM5-e.2: circle-color artık data-driven case (is_metrobus → antrasit,
  // else sarı). Sabit renk değil; case yapısı doğrulanır.
  it('uses a data-driven case for circle-color (KM5-e.2: is_metrobus → antrasit, else sarı)', () => {
    const color = buildFleetPaint()['circle-color'] as readonly unknown[];
    expect(Array.isArray(color)).toBe(true);
    expect(color[0]).toBe('case');
    expect(color[1]).toEqual(['==', ['get', 'is_metrobus'], true]);
    expect(color[2]).toBe('#3A3D40');                  // antrasit
    expect(color[3]).toBe(MODE_FALLBACK_COLORS.bus);   // sarı default (eski sabit)
  });

  it('falls back to yellow when is_metrobus is missing/false (defansif case fallback)', () => {
    // Inline evaluator: case [==, ['get', 'is_metrobus'], true] → then : else
    const expr = buildFleetPaint()['circle-color'] as readonly [
      'case', readonly unknown[], string, string,
    ];
    const evalCase = (props: Record<string, unknown>): string =>
      props.is_metrobus === true ? expr[2] : expr[3];
    expect(evalCase({})).toBe(MODE_FALLBACK_COLORS.bus);
    expect(evalCase({ is_metrobus: false })).toBe(MODE_FALLBACK_COLORS.bus);
    expect(evalCase({ is_metrobus: true })).toBe('#3A3D40');
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

  it('focused dolu → circle-opacity case ["in" literal] expression', () => {
    const paint = buildFleetPaint(['iett:29B']) as Record<string, unknown>;
    const op = paint['circle-opacity'] as readonly unknown[];
    expect(op[0]).toBe('case');
    expect(op[1]).toEqual(['in', ['get', 'route_id'], ['literal', ['iett:29B']]]);
    expect(op[2]).toBe(1.0);
    expect(op[3]).toBe(0.2);
  });

  it('focused multi-id (variant group) → all 7 variant ids in literal', () => {
    const ids = ['iett:1562', 'iett:1564', 'iett:1567', 'iett:52301', 'iett:52303', 'iett:55379'];
    const paint = buildFleetPaint(ids) as Record<string, unknown>;
    const op = paint['circle-opacity'] as readonly unknown[];
    const literal = (op[1] as readonly unknown[])[2] as readonly unknown[];
    expect(literal[1]).toEqual(ids);
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

// KM5-e.2: filter expression iki bağımsız toggle (busVisible, metrobusVisible).
// case [==, ['get', 'is_metrobus'], true] metrobusVisible : busVisible.
describe('buildFleetFilter', () => {
  it('returns a case expression on is_metrobus', () => {
    const f = buildFleetFilter(true, true) as readonly unknown[];
    expect(f[0]).toBe('case');
    expect(f[1]).toEqual(['==', ['get', 'is_metrobus'], true]);
  });

  it('reflects busVisible in else branch and metrobusVisible in then branch', () => {
    const f1 = buildFleetFilter(true, false) as readonly unknown[];
    expect(f1[2]).toBe(false); // metrobus gizli
    expect(f1[3]).toBe(true);  // bus görünür
    const f2 = buildFleetFilter(false, true) as readonly unknown[];
    expect(f2[2]).toBe(true);
    expect(f2[3]).toBe(false);
  });

  it('both false hides everything', () => {
    const f = buildFleetFilter(false, false) as readonly unknown[];
    expect(f[2]).toBe(false);
    expect(f[3]).toBe(false);
  });
});
