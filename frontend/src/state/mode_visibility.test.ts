import { describe, expect, it, vi } from 'vitest';
import {
  ALL_MODES,
  FILTER_NEVER,
  ModeVisibility,
  getFilterExpression,
} from './mode_visibility';

describe('ModeVisibility', () => {
  it('starts with every mode visible', () => {
    const mv = new ModeVisibility();
    for (const m of ALL_MODES) expect(mv.isVisible(m)).toBe(true);
  });

  it('toggle hides then re-shows a mode', () => {
    const mv = new ModeVisibility();
    mv.toggle('metro');
    expect(mv.isVisible('metro')).toBe(false);
    mv.toggle('metro');
    expect(mv.isVisible('metro')).toBe(true);
  });

  it('fires subscribed listeners on every toggle', () => {
    const mv = new ModeVisibility();
    const spy = vi.fn();
    mv.subscribe(spy);
    mv.toggle('ferry');
    mv.toggle('ferry');
    expect(spy).toHaveBeenCalledTimes(2);
    expect(spy.mock.calls[0][0].has('ferry')).toBe(false);
    expect(spy.mock.calls[1][0].has('ferry')).toBe(true);
  });
});

describe('getFilterExpression', () => {
  it('returns null when every mode is visible (no-op filter)', () => {
    const mv = new ModeVisibility();
    expect(getFilterExpression(mv.getVisible())).toBeNull();
  });

  it('returns FILTER_NEVER when no mode is visible', () => {
    const mv = new ModeVisibility();
    for (const m of ALL_MODES) mv.toggle(m);
    expect(getFilterExpression(mv.getVisible())).toEqual(FILTER_NEVER);
  });

  it('returns ["in", ["get","mode"], ["literal", [...]]] for a mixed set', () => {
    const mv = new ModeVisibility();
    mv.toggle('metro');
    mv.toggle('tram');
    const expr = getFilterExpression(mv.getVisible()) as unknown[];
    expect(Array.isArray(expr)).toBe(true);
    expect(expr[0]).toBe('in');
    expect(expr[1]).toEqual(['get', 'mode']);
    const literal = expr[2] as unknown[];
    expect(literal[0]).toBe('literal');
    const set = new Set(literal[1] as string[]);
    expect(set.has('metro')).toBe(false);
    expect(set.has('tram')).toBe(false);
    expect(set.has('marmaray')).toBe(true);
    expect(set.has('funicular')).toBe(true);
    expect(set.has('ferry')).toBe(true);
  });

  it('returns FILTER_NEVER as a ["==", "__none__"] expression (sanity)', () => {
    expect(FILTER_NEVER).toEqual(['==', ['get', 'mode'], '__none__']);
  });
});
