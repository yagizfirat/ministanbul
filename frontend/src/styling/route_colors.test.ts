import { describe, expect, it } from 'vitest';
import {
  ROUTE_COLORS,
  MODE_FALLBACK_COLORS,
  getRouteColor,
  lighten,
} from './route_colors';

describe('getRouteColor', () => {
  it('returns the canonical hex from ROUTE_COLORS for a known line', () => {
    expect(getRouteColor('M2', 'metro')).toBe(ROUTE_COLORS.M2);
  });

  it('normalizes lowercase short_name to uppercase before lookup', () => {
    expect(getRouteColor('m2', 'metro')).toBe(ROUTE_COLORS.M2);
  });

  it('trims and normalizes mixed-case short_name', () => {
    expect(getRouteColor('  T1 ', 'tram')).toBe(ROUTE_COLORS.T1);
  });

  it('falls back to mode color for an unknown bus line', () => {
    expect(getRouteColor('29B', 'bus')).toBe(MODE_FALLBACK_COLORS.bus);
  });

  it('falls back to a default color for an unknown line and unknown mode', () => {
    const out = getRouteColor('UNKNOWN', 'unknown_mode');
    expect(out).toMatch(/^#[0-9A-F]{6}$/i);
    expect(out).not.toBe(ROUTE_COLORS.M2);
  });

  it('uses the funicular fallback (no F-line in ROUTE_COLORS yet)', () => {
    expect(getRouteColor('F1', 'funicular')).toBe(MODE_FALLBACK_COLORS.funicular);
  });
});

describe('lighten', () => {
  it('produces a lighter hex than the input for a saturated mid-tone color', () => {
    const orig = '#009E4F';
    const out = lighten(orig, 0.2);
    expect(out).toMatch(/^#[0-9A-F]{6}$/);
    expect(out).not.toBe(orig);
    // L increases → channel sum should increase (rough but reliable for mid tones).
    const sum = (h: string) =>
      parseInt(h.slice(1, 3), 16) +
      parseInt(h.slice(3, 5), 16) +
      parseInt(h.slice(5, 7), 16);
    expect(sum(out)).toBeGreaterThan(sum(orig));
  });

  it('two lighten calls give different results (not idempotent)', () => {
    const once = lighten('#009E4F', 0.2);
    const twice = lighten(once, 0.2);
    expect(twice).not.toBe(once);
  });

  it('lifts black to mid-gray for amount=0.5', () => {
    expect(lighten('#000000', 0.5)).toBe('#808080');
  });

  it('clamps L at 1 (white) and does not overshoot', () => {
    expect(lighten('#FFFFFF', 0.5)).toBe('#FFFFFF');
  });

  it('returns a 7-char #RRGGBB string for any input', () => {
    for (const hex of ['#EE2229', '#059A4D', '#FCD10D']) {
      const out = lighten(hex, 0.1);
      expect(out).toHaveLength(7);
      expect(out.startsWith('#')).toBe(true);
    }
  });
});
