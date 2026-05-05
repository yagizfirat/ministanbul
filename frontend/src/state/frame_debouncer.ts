// Coalesce repeated calls into a single requestAnimationFrame tick so
// rapid bursts (Reset, Tümü, Hiçbiri, fast checkbox toggles) cause one
// MapLibre setFilter call instead of N. Scheduler is injectable for
// tests (sync or fake-timer schedulers).
//
// Usage:
//   const debouncedApply = debounceFrame(applyFilters);
//   routeVisibility.subscribe(debouncedApply);

export type FrameScheduler = (cb: () => void) => void;

const defaultScheduler: FrameScheduler = (cb) => {
  // setTimeout fallback for SSR / test environments without rAF.
  if (typeof requestAnimationFrame === 'function') {
    requestAnimationFrame(cb);
  } else {
    setTimeout(cb, 0);
  }
};

export function debounceFrame(
  fn: () => void,
  scheduler: FrameScheduler = defaultScheduler,
): () => void {
  let scheduled = false;
  return () => {
    if (scheduled) return;
    scheduled = true;
    scheduler(() => {
      scheduled = false;
      fn();
    });
  };
}
