// KM-e Fix-A (Spec Ek A.19 borç #7): MapLibre setFilter chain'ini
// requestAnimationFrame'e debounce et. Reset / Tümü / Hiçbiri /
// hızlı checkbox toggle gibi operasyonlarda RouteVisibility.fire()
// üst üste tetiklenirse, listener'lar (applyFilters, syncCheckboxes)
// tek bir frame'de toplanıp bir kere çalışır. setFilter + setData
// pipeline çakışması ve cumulative paint maliyeti azalır.
//
// Kullanım:
//   const debouncedApply = debounceFrame(applyFilters);
//   routeVisibility.subscribe(debouncedApply);
//
// Test edilebilirlik için scheduler injection: testte requestAnimationFrame
// yerine sync scheduler ya da fake timer geçilebilir.

export type FrameScheduler = (cb: () => void) => void;

const defaultScheduler: FrameScheduler = (cb) => {
  // SSR / test ortamlarında requestAnimationFrame yoksa setTimeout fallback.
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
