import { describe, expect, it } from 'vitest';
import { combineFilters } from './composite_filter';
import { FILTER_NEVER as MODE_NEVER } from './mode_visibility';
import { FILTER_NEVER as ROUTE_NEVER } from './route_visibility';

describe('combineFilters', () => {
  it('returns null when both inputs are null', () => {
    expect(combineFilters(null, null)).toBeNull();
  });

  it('returns the right filter when the left is null', () => {
    const right = ['in', ['get', 'route_id'], ['literal', ['M2']]];
    expect(combineFilters(null, right)).toEqual(right);
  });

  it('returns the left filter when the right is null', () => {
    const left = ['in', ['get', 'mode'], ['literal', ['metro']]];
    expect(combineFilters(left, null)).toEqual(left);
  });

  it('wraps both inputs in an "all" expression when both are non-null', () => {
    const a = ['in', ['get', 'mode'], ['literal', ['metro']]];
    const b = ['in', ['get', 'route_id'], ['literal', ['M2']]];
    expect(combineFilters(a, b)).toEqual(['all', a, b]);
  });

  it('cascades through FILTER_NEVER from mode_visibility (mode hides everything)', () => {
    expect(combineFilters(MODE_NEVER, null)).toEqual(MODE_NEVER);
  });

  it('combines mode-never with route-never (cascade hides everything via "all")', () => {
    const out = combineFilters(MODE_NEVER, ROUTE_NEVER);
    expect(out).toEqual(['all', MODE_NEVER, ROUTE_NEVER]);
  });
});
