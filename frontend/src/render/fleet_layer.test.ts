import { describe, expect, it } from 'vitest';
import { buildFleetPaint } from './fleet_layer';

describe('buildFleetPaint', () => {
  it('returns a circle paint spec with all required keys', () => {
    const paint = buildFleetPaint();
    expect(paint['circle-radius']).toBeTruthy();
    expect(paint['circle-color']).toBeTruthy();
    expect(paint['circle-stroke-width']).toBeDefined();
    expect(paint['circle-stroke-color']).toBeTruthy();
  });

  it('binds circle-color to the per-feature color property', () => {
    const paint = buildFleetPaint();
    expect(paint['circle-color']).toEqual(['get', 'color']);
  });

  it('uses an interpolate expression for circle-radius (zoom-driven)', () => {
    const radius = buildFleetPaint()['circle-radius'];
    expect(Array.isArray(radius)).toBe(true);
    expect(radius[0]).toBe('interpolate');
  });
});
