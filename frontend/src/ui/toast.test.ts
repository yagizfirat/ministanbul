// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { _resetToastForTests, showToast } from './toast';

afterEach(() => {
  _resetToastForTests();
  vi.useRealTimers();
});

describe('showToast', () => {
  it('appends a single .toast element to document.body and sets visible', () => {
    showToast('hello');
    const toasts = document.querySelectorAll('.toast');
    expect(toasts.length).toBe(1);
    const t = toasts[0] as HTMLElement;
    expect(t.textContent).toBe('hello');
    expect(t.dataset.visible).toBe('true');
  });

  it('reuses the same element on a second call (no DOM duplication)', () => {
    showToast('first');
    showToast('second');
    const toasts = document.querySelectorAll('.toast');
    expect(toasts.length).toBe(1);
    expect((toasts[0] as HTMLElement).textContent).toBe('second');
  });

  it('hides the toast after the duration elapses', () => {
    vi.useFakeTimers();
    showToast('temp', 1000);
    const t = document.querySelector('.toast') as HTMLElement;
    expect(t.dataset.visible).toBe('true');
    vi.advanceTimersByTime(1100);
    expect(t.dataset.visible).toBe('false');
  });

  it('resets the timer on a second call (does not hide early)', () => {
    vi.useFakeTimers();
    showToast('a', 1000);
    vi.advanceTimersByTime(800);
    showToast('b', 1000);
    vi.advanceTimersByTime(800); // toplam 1600 ama 2. çağrı reset etti
    const t = document.querySelector('.toast') as HTMLElement;
    expect(t.dataset.visible).toBe('true');
    vi.advanceTimersByTime(300);
    expect(t.dataset.visible).toBe('false');
  });
});
