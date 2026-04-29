const COLOR_FRESH = '#16a34a';   // <90s
const COLOR_STALE = '#ca8a04';   // 90-180s
const COLOR_DEAD = '#dc2626';    // >180s

const THRESHOLD_STALE_S = 90;
const THRESHOLD_DEAD_S = 180;

export interface LastUpdateIndicator {
  setTimestamp(dataTimeMs: number | null): void;
  destroy(): void;
}

export function createLastUpdateIndicator(): LastUpdateIndicator {
  const el = document.createElement('div');
  el.style.cssText = [
    'position: fixed',
    'top: 12px',
    'left: 12px',
    'padding: 6px 10px',
    'border-radius: 6px',
    'background: rgba(255, 255, 255, 0.92)',
    'font: 12px/1.2 system-ui, -apple-system, sans-serif',
    'color: #111',
    'box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2)',
    'z-index: 1000',
    'pointer-events: none',
  ].join(';');
  el.textContent = 'Veri bekleniyor…';
  document.body.appendChild(el);

  let lastDataTime: number | null = null;

  function render(): void {
    if (lastDataTime === null) {
      el.textContent = 'Veri bekleniyor…';
      el.style.borderLeft = `4px solid ${COLOR_DEAD}`;
      return;
    }
    const ageS = Math.max(0, Math.round((Date.now() - lastDataTime) / 1000));
    const color =
      ageS < THRESHOLD_STALE_S ? COLOR_FRESH :
      ageS < THRESHOLD_DEAD_S ? COLOR_STALE : COLOR_DEAD;
    el.textContent = `Son güncelleme: ${ageS} sn önce`;
    el.style.borderLeft = `4px solid ${color}`;
  }

  const tick = setInterval(render, 1000);

  return {
    setTimestamp(dataTimeMs: number | null): void {
      lastDataTime = dataTimeMs;
      render();
    },
    destroy(): void {
      clearInterval(tick);
      el.remove();
    },
  };
}
