import { describe, expect, it, vi } from 'vitest';
import {
  FILTER_NEVER,
  RouteVisibility,
  getFilterExpression,
} from './route_visibility';

const ALL = ['public:m1a', 'public:m2', 'public:m3', 'iett:1', 'iett:29B'];
const DEFAULT_VISIBLE = ['public:m1a', 'public:m2', 'public:m3']; // bus default hidden

function fresh(): RouteVisibility {
  return new RouteVisibility(ALL, DEFAULT_VISIBLE);
}

describe('RouteVisibility', () => {
  it('starts with the initial visible set, not all routes', () => {
    const rv = fresh();
    expect(rv.isVisible('public:m2')).toBe(true);
    expect(rv.isVisible('iett:1')).toBe(false);
    expect(rv.getTotalCount()).toBe(ALL.length);
  });

  it('toggle hides then re-shows a route', () => {
    const rv = fresh();
    rv.toggle('public:m2');
    expect(rv.isVisible('public:m2')).toBe(false);
    rv.toggle('public:m2');
    expect(rv.isVisible('public:m2')).toBe(true);
  });

  it('setVisible no-ops when the desired state already holds', () => {
    const rv = fresh();
    const spy = vi.fn();
    rv.subscribe(spy);
    rv.setVisible('public:m2', true); // already visible
    rv.setVisible('iett:1', false);   // already hidden
    expect(spy).not.toHaveBeenCalled();
  });

  it('setBulkVisible fires the listener exactly once for many routes', () => {
    const rv = fresh();
    const spy = vi.fn();
    rv.subscribe(spy);
    rv.setBulkVisible(['iett:1', 'iett:29B'], true);
    expect(spy).toHaveBeenCalledTimes(1);
    expect(rv.isVisible('iett:1')).toBe(true);
    expect(rv.isVisible('iett:29B')).toBe(true);
  });

  it('setBulkVisible does not fire when nothing changes', () => {
    const rv = fresh();
    const spy = vi.fn();
    rv.subscribe(spy);
    rv.setBulkVisible(['public:m2'], true); // already visible
    expect(spy).not.toHaveBeenCalled();
  });

  it('listeners receive an independent snapshot, not the live set', () => {
    const rv = fresh();
    const spy = vi.fn();
    rv.subscribe(spy);
    rv.toggle('iett:1');
    rv.toggle('iett:1');
    expect(spy).toHaveBeenCalledTimes(2);
    expect(spy.mock.calls[0][0].has('iett:1')).toBe(true);
    expect(spy.mock.calls[1][0].has('iett:1')).toBe(false);
  });
});

describe('getFilterExpression', () => {
  it('returns null when every route is visible (no-op filter)', () => {
    const rv = new RouteVisibility(ALL, ALL);
    expect(getFilterExpression(rv.getVisible(), rv.getTotalCount())).toBeNull();
  });

  it('returns FILTER_NEVER when no route is visible', () => {
    const rv = new RouteVisibility(ALL, []);
    expect(getFilterExpression(rv.getVisible(), rv.getTotalCount())).toEqual(FILTER_NEVER);
  });

  it('returns ["in", ["get","route_id"], ["literal", [...]]] for a mixed set', () => {
    const rv = fresh();
    const expr = getFilterExpression(rv.getVisible(), rv.getTotalCount()) as unknown[];
    expect(Array.isArray(expr)).toBe(true);
    expect(expr[0]).toBe('in');
    expect(expr[1]).toEqual(['get', 'route_id']);
    const literal = expr[2] as unknown[];
    expect(literal[0]).toBe('literal');
    const set = new Set(literal[1] as string[]);
    expect(set).toEqual(new Set(DEFAULT_VISIBLE));
  });

  it('FILTER_NEVER targets route_id (sanity vs mode_visibility)', () => {
    expect(FILTER_NEVER).toEqual(['==', ['get', 'route_id'], '__none__']);
  });
});

describe('RouteVisibility.expandTotalCount (bus lazy fetch)', () => {
  it('grows totalCount and does not fire listeners', () => {
    const rv = fresh();
    const spy = vi.fn();
    rv.subscribe(spy);
    const before = rv.getTotalCount();
    rv.expandTotalCount(9275);
    expect(rv.getTotalCount()).toBe(before + 9275);
    expect(spy).not.toHaveBeenCalled();
  });

  it('keeps the visible set untouched (newly counted routes stay hidden)', () => {
    const rv = fresh();
    const visibleBefore = Array.from(rv.getVisible());
    rv.expandTotalCount(9275);
    expect(Array.from(rv.getVisible())).toEqual(visibleBefore);
  });

  it('makes getFilterExpression keep returning a non-null filter after expansion', () => {
    const rv = fresh();
    // 5 routes, 3 visible → mixed → ['in', ...]
    expect(getFilterExpression(rv.getVisible(), rv.getTotalCount())).not.toBeNull();
    rv.expandTotalCount(9275);
    // Hâlâ mixed (3 visible / 9280 total) → ['in', ...]
    expect(getFilterExpression(rv.getVisible(), rv.getTotalCount())).not.toBeNull();
  });
});
