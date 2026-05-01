import { describe, expect, it, vi } from 'vitest';
import { RouteFocus } from './route_focus';

describe('RouteFocus', () => {
  it('starts with null focus', () => {
    const f = new RouteFocus();
    expect(f.getFocused()).toBeNull();
  });

  it('setFocus updates state and fires listeners', () => {
    const f = new RouteFocus();
    const spy = vi.fn();
    f.subscribe(spy);
    f.setFocus('public:m2');
    expect(f.getFocused()).toBe('public:m2');
    expect(spy).toHaveBeenCalledTimes(1);
    expect(spy).toHaveBeenCalledWith('public:m2');
  });

  it('setFocus is a no-op when state already matches (no listener fire)', () => {
    const f = new RouteFocus();
    const spy = vi.fn();
    f.setFocus('public:m2'); // initial set
    f.subscribe(spy);
    f.setFocus('public:m2'); // same id again
    expect(spy).not.toHaveBeenCalled();
  });

  it('setFocus(null) clears the focus and fires', () => {
    const f = new RouteFocus();
    const spy = vi.fn();
    f.setFocus('public:m2');
    f.subscribe(spy);
    f.setFocus(null);
    expect(f.getFocused()).toBeNull();
    expect(spy).toHaveBeenCalledWith(null);
  });

  it('toggle on the same id clears it; toggle on a new id replaces', () => {
    const f = new RouteFocus();
    f.toggle('public:m2');
    expect(f.getFocused()).toBe('public:m2');
    f.toggle('public:m2');
    expect(f.getFocused()).toBeNull();
    f.toggle('public:m2');
    f.toggle('public:m1a');
    expect(f.getFocused()).toBe('public:m1a');
  });

  it('multiple subscribers each receive independent calls', () => {
    const f = new RouteFocus();
    const a = vi.fn();
    const b = vi.fn();
    f.subscribe(a);
    f.subscribe(b);
    f.setFocus('public:t1');
    expect(a).toHaveBeenCalledTimes(1);
    expect(b).toHaveBeenCalledTimes(1);
  });
});
