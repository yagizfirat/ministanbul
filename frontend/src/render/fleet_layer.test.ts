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

  // v0.8.2 KM-c: 3-branch case. Metrobüs öncelikli kontrol (route_id
  // genelde null, eski `has route_id` branch'i metrobüsü kaçırırdı).
  it('drives circle-stroke-width via a 3-branch case (metrobus → mapped → unmapped)', () => {
    const w = buildFleetPaint()['circle-stroke-width'] as readonly unknown[];
    expect(Array.isArray(w)).toBe(true);
    expect(w[0]).toBe('case');
    expect(w[1]).toEqual(['==', ['get', 'is_metrobus'], true]);
    expect(w[2]).toBe(1.5); // metrobus → border
    expect(w[3]).toEqual(['has', 'route_id']);
    expect(w[4]).toBe(1.5); // mapped bus → border
    expect(w[5]).toBe(0);   // unmapped bus → no border
  });

  it('uses an interpolate expression for circle-radius (zoom-driven)', () => {
    const radius = buildFleetPaint()['circle-radius'];
    expect(Array.isArray(radius)).toBe(true);
    expect(radius[0]).toBe('interpolate');
  });

  // v0.8.2 KM-c + v0.8.3 KM-b LOD: zoom 7→0 (gizli), zoom 9 küçük case,
  // zoom 10/14 mevcut KM-c case. Stops: [7, 0], [9, case], [10, case],
  // [14, case].
  it('circle-radius LOD stops: zoom 7=0 (hidden), 9=case, 10=case, 14=case', () => {
    const radius = buildFleetPaint()['circle-radius'] as readonly unknown[];
    expect(radius[0]).toBe('interpolate');
    expect(radius[1]).toEqual(['linear']);
    expect(radius[2]).toEqual(['zoom']);
    // Stop 1: zoom 7, value 0 (LOD cull)
    expect(radius[3]).toBe(7);
    expect(radius[4]).toBe(0);
    // Stop 2: zoom 9, value case (metrobus 2, default 1)
    expect(radius[5]).toBe(9);
    const at9 = radius[6] as readonly unknown[];
    expect(at9[0]).toBe('case');
    expect([at9[2], at9[3]]).toEqual([2, 1]);
    // Stop 3: zoom 10, value case (metrobus 4, default 3) — KM-c
    expect(radius[7]).toBe(10);
    const at10 = radius[8] as readonly unknown[];
    expect([at10[2], at10[3]]).toEqual([4, 3]);
    // Stop 4: zoom 14, value case (metrobus 7, default 6) — KM-c
    expect(radius[9]).toBe(14);
    const at14 = radius[10] as readonly unknown[];
    expect([at14[2], at14[3]]).toEqual([7, 6]);
  });

  it('circle-radius LOD: stops are monotonically non-decreasing for the default branch', () => {
    // LOD anlam kontrolü: 0 → 1 → 3 → 6 (default), 0 → 2 → 4 → 7 (metrobus)
    const radius = buildFleetPaint()['circle-radius'] as readonly unknown[];
    const evalCase = (stop: unknown, isMetrobus: boolean): number => {
      if (typeof stop === 'number') return stop;
      const c = stop as readonly unknown[];
      return (isMetrobus ? c[2] : c[3]) as number;
    };
    const defaults = [radius[4], radius[6], radius[8], radius[10]].map((s) =>
      evalCase(s, false),
    );
    const metro = [radius[4], radius[6], radius[8], radius[10]].map((s) =>
      evalCase(s, true),
    );
    expect(defaults).toEqual([0, 1, 3, 6]);
    expect(metro).toEqual([0, 2, 4, 7]);
  });

  it('KM-a regression guard: ["zoom"] does not appear nested inside circle-radius case stops', () => {
    // MapLibre style spec: ["zoom"] yalnız top-level interpolate input'u.
    // case içinde nested ["zoom"] → setPaintProperty runtime Error.
    const r = buildFleetPaint()['circle-radius'] as readonly unknown[];
    const hasNestedZoom = (node: unknown, depth: number): boolean => {
      if (!Array.isArray(node)) return false;
      if (depth > 0 && node.length === 1 && node[0] === 'zoom') return true;
      return node.some((c) => hasNestedZoom(c, depth + 1));
    };
    const stops = r.slice(3);
    for (let i = 1; i < stops.length; i += 2) {
      expect(hasNestedZoom(stops[i], 0)).toBe(false);
    }
  });

  it('circle-stroke-color is a case: metrobus → white, default → koyu kahve', () => {
    const c = buildFleetPaint()['circle-stroke-color'] as readonly unknown[];
    expect(c[0]).toBe('case');
    expect(c[1]).toEqual(['==', ['get', 'is_metrobus'], true]);
    expect(c[2]).toBe('#FFFFFF');
    expect(c[3]).toBe('#3a2a00');
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

  it('manually evaluates the 3-branch stroke-width case for metrobus / mapped / unmapped', () => {
    // KM-c: case [is_metrobus → 1.5] ; case [has route_id → 1.5] ; else 0.
    const expr = buildFleetPaint()['circle-stroke-width'] as readonly unknown[];
    const ev = (props: Record<string, unknown>): number => {
      // [case, isMetrobusCase, w_metrobus, hasRouteIdCase, w_mapped, w_unmapped]
      if (props.is_metrobus === true) return expr[2] as number;
      if ('route_id' in props) return expr[4] as number;
      return expr[5] as number;
    };
    expect(ev({ id: 'x', is_metrobus: true })).toBe(1.5);
    expect(ev({ id: 'x', route_id: '34A' })).toBe(1.5);
    expect(ev({ id: 'x' })).toBe(0); // unmapped bus
    // Metrobus + null route_id (gerçek senaryo) → border korunur
    expect(ev({ id: 'x', is_metrobus: true })).toBe(1.5);
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
