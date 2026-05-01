import { describe, expect, it, vi } from 'vitest';
import { RouteFocus } from './route_focus';

describe('RouteFocus', () => {
  it('starts with null focus', () => {
    const f = new RouteFocus();
    expect(f.getFocused()).toBeNull();
  });

  it('setFocus with a single id stores a 1-element array', () => {
    const f = new RouteFocus();
    f.setFocus(['public:m2']);
    expect(f.getFocused()).toEqual(['public:m2']);
  });

  it('setFocus with multiple ids stores them all (variant group focus)', () => {
    const f = new RouteFocus();
    f.setFocus(['iett:1562', 'iett:1564', 'iett:1567']);
    expect(f.getFocused()).toEqual(['iett:1562', 'iett:1564', 'iett:1567']);
  });

  it('setFocus is a no-op when array contents are equal (same id list)', () => {
    const f = new RouteFocus();
    const spy = vi.fn();
    f.setFocus(['public:m2']);
    f.subscribe(spy);
    f.setFocus(['public:m2']); // same single-id
    expect(spy).not.toHaveBeenCalled();
  });

  it('setFocus fires when array contents differ (even same length)', () => {
    const f = new RouteFocus();
    const spy = vi.fn();
    f.setFocus(['a']);
    f.subscribe(spy);
    f.setFocus(['b']);
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it('setFocus(null) clears the focus and fires', () => {
    const f = new RouteFocus();
    const spy = vi.fn();
    f.setFocus(['public:m2']);
    f.subscribe(spy);
    f.setFocus(null);
    expect(f.getFocused()).toBeNull();
    expect(spy).toHaveBeenCalledWith(null);
  });

  it('toggle on the same array clears it; toggle on a new array replaces', () => {
    const f = new RouteFocus();
    f.toggle(['public:m2']);
    expect(f.getFocused()).toEqual(['public:m2']);
    f.toggle(['public:m2']);
    expect(f.getFocused()).toBeNull();
    f.toggle(['public:m2']);
    f.toggle(['public:m1a']);
    expect(f.getFocused()).toEqual(['public:m1a']);
  });

  it('toggle on a multi-id group clears it on second call', () => {
    const f = new RouteFocus();
    const ids = ['iett:1562', 'iett:1564'];
    f.toggle(ids);
    expect(f.getFocused()).toEqual(ids);
    f.toggle(ids);
    expect(f.getFocused()).toBeNull();
  });

  it('multiple subscribers each receive independent calls', () => {
    const f = new RouteFocus();
    const a = vi.fn();
    const b = vi.fn();
    f.subscribe(a);
    f.subscribe(b);
    f.setFocus(['public:t1']);
    expect(a).toHaveBeenCalledTimes(1);
    expect(b).toHaveBeenCalledTimes(1);
  });
});
