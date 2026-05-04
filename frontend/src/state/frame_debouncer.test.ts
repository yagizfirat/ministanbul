import { describe, expect, it, vi } from 'vitest';
import { debounceFrame, type FrameScheduler } from './frame_debouncer';

// Sync scheduler — testlerde RAF'ı taklit eder, callback'i hemen
// çalıştırmak yerine kuyruğa alır ve flush() ile manuel tetikler.
function makeManualScheduler(): {
  scheduler: FrameScheduler;
  flush(): void;
  pendingCount(): number;
} {
  const queue: Array<() => void> = [];
  return {
    scheduler: (cb) => { queue.push(cb); },
    flush(): void {
      const calls = queue.splice(0, queue.length);
      for (const c of calls) c();
    },
    pendingCount: () => queue.length,
  };
}

describe('debounceFrame', () => {
  it('runs the underlying fn once when scheduled multiple times in the same frame', () => {
    const m = makeManualScheduler();
    const fn = vi.fn();
    const debounced = debounceFrame(fn, m.scheduler);
    debounced();
    debounced();
    debounced();
    debounced();
    expect(fn).not.toHaveBeenCalled();   // henüz frame fire olmadı
    expect(m.pendingCount()).toBe(1);    // sadece 1 RAF kuyruğu
    m.flush();
    expect(fn).toHaveBeenCalledTimes(1); // tek çağrı
  });

  it('reschedules after a frame fires (subsequent calls trigger a new frame)', () => {
    const m = makeManualScheduler();
    const fn = vi.fn();
    const debounced = debounceFrame(fn, m.scheduler);
    debounced();
    m.flush();
    expect(fn).toHaveBeenCalledTimes(1);
    debounced();
    debounced();
    m.flush();
    expect(fn).toHaveBeenCalledTimes(2); // ikinci frame'de bir kez daha
  });

  it('does not call fn if it is never scheduled', () => {
    const m = makeManualScheduler();
    const fn = vi.fn();
    debounceFrame(fn, m.scheduler);
    m.flush();
    expect(fn).not.toHaveBeenCalled();
  });

  // KM-e simulation: RouteVisibility üzerinde 3 ardışık state değişimi
  // (örn. 3 hat checkbox flip) tek frame'e sıkışıp 3 setFilter setine
  // değil, 1 setFilter setine düşmeli. Layer başına 3 setFilter (route-
  // lines, scheduled-circles) toplam 6 → debounced sonrası 2 (1 frame ×
  // 2 layer call) düşer.
  it('simulates Reset/multi-toggle scenario: N rapid changes → 1 fn run per frame', () => {
    const m = makeManualScheduler();
    const setFilterCalls: string[] = [];
    const applyFn = (): void => {
      setFilterCalls.push('route-lines');
      setFilterCalls.push('scheduled-circles');
    };
    const debounced = debounceFrame(applyFn, m.scheduler);
    // Reset + 5 manuel checkbox flip = 6 fire
    for (let i = 0; i < 6; i++) debounced();
    expect(setFilterCalls).toHaveLength(0); // hiçbiri henüz çağrılmadı
    m.flush();
    expect(setFilterCalls).toHaveLength(2); // tek frame, 2 layer
  });
});
