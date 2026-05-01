// Faz 5 KM4 — informational chip explaining the colored vehicle dots are
// schedule-based simulation, not live positions. Top-right, below the
// MapLibre NavigationControl.

const HINT_TEXT =
  'Renkli noktalar gerçek konum değil, GTFS tarifesine göre tahmini ' +
  'konumdur. Gerçek gecikme/aksaklık yansıtılmaz.';

interface ModeRow {
  key: string;
  label: string;
  fill: string;
  stroke: string;
}

// Hardcoded to keep this file CSS-only-in-JS without pulling the runtime
// palette through an import indirection (per project decision).
const MODES: ModeRow[] = [
  { key: 'metro', label: 'Metro', fill: '#60a5fa', stroke: '#1e3a8a' },
  { key: 'marmaray', label: 'Marmaray', fill: '#c084fc', stroke: '#6b21a8' },
  { key: 'tram', label: 'Tramvay', fill: '#4ade80', stroke: '#166534' },
  { key: 'funicular', label: 'Füniküler', fill: '#fb923c', stroke: '#9a3412' },
  { key: 'ferry', label: 'Vapur', fill: '#22d3ee', stroke: '#155e75' },
];

export function createSimulatedBadge(): HTMLElement {
  const container = document.createElement('div');
  container.style.cssText = [
    'position: fixed',
    // 144px clears the MapLibre NavigationControl (zoom + compass + pitch
    // ~ 129px tall) plus a small gap.
    'top: 144px',
    'right: 12px',
    'padding: 6px 10px',
    'border-radius: 8px',
    'background: rgba(15, 23, 42, 0.85)',
    'color: #e2e8f0',
    'font: 12px/1.2 system-ui, -apple-system, sans-serif',
    'display: flex',
    'align-items: center',
    'gap: 6px',
    'z-index: 1000',
    'user-select: none',
    'backdrop-filter: blur(4px)',
    '-webkit-backdrop-filter: blur(4px)',
  ].join(';');

  for (const m of MODES) {
    const dot = document.createElement('span');
    dot.title = m.label;
    dot.style.cssText = [
      'display: inline-block',
      'width: 8px',
      'height: 8px',
      'border-radius: 50%',
      `background: ${m.fill}`,
      `border: 1px solid ${m.stroke}`,
    ].join(';');
    container.appendChild(dot);
  }

  const label = document.createElement('span');
  label.textContent = 'Tarife-bazlı simülasyon';
  label.style.marginLeft = '4px';
  container.appendChild(label);

  const hint = document.createElement('span');
  hint.textContent = '?';
  hint.title = HINT_TEXT;
  hint.style.cssText = [
    'display: inline-block',
    'width: 14px',
    'height: 14px',
    'border-radius: 50%',
    'background: rgba(148, 163, 184, 0.3)',
    'color: #cbd5e1',
    'font-size: 10px',
    'line-height: 14px',
    'text-align: center',
    'cursor: help',
    'margin-left: 2px',
  ].join(';');
  container.appendChild(hint);

  document.body.appendChild(container);
  return container;
}
