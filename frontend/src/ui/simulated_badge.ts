// Faz 5 KM4 — informational chip explaining the colored vehicle dots are
// schedule-based simulation, not live positions. Top-right, below the
// MapLibre NavigationControl.
//
// Faz 6 KM1 alt-iş e — chip dot'ları:
//   (i) MODE_FALLBACK_COLORS'a hizalandı (ekrandaki gerçek nokta paleti
//       ile aynı kaynak; alt-iş c sonrası mode_colors.ts silindi),
//   (ii) tıklanabilir hale geldi → mode_visibility state'i toggle eder.

import { MODE_FALLBACK_COLORS, lighten } from '../styling/route_colors';
import { ALL_MODES, type ModeKey } from '../state/mode_visibility';

const HINT_TEXT =
  'Renkli noktalar gerçek konum değil, GTFS tarifesine göre tahmini ' +
  'konumdur. Gerçek gecikme/aksaklık yansıtılmaz.';

const LABELS: Record<ModeKey, string> = {
  metro: 'Metro',
  marmaray: 'Marmaray',
  tram: 'Tramvay',
  funicular: 'Füniküler',
  ferry: 'Vapur',
};

// Stroke for chip dot = lighten(fill, -0.15) — fill'in koyu kenarı.
// Alt-iş a/c'de fill = MODE_FALLBACK_COLORS[mode]; chip dot böylece
// scheduled vehicle paletinin minyatür temsilidir.
const STROKE_DARKEN = -0.15;

export interface SimulatedBadgeOptions {
  onToggle: (mode: ModeKey) => void;
  isVisible: (mode: ModeKey) => boolean;
}

export interface SimulatedBadgeHandle {
  element: HTMLElement;
  syncVisibility(): void;
}

export function createSimulatedBadge(
  opts: SimulatedBadgeOptions,
): SimulatedBadgeHandle {
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

  const dotByMode = new Map<ModeKey, HTMLElement>();

  for (const mode of ALL_MODES) {
    const dot = document.createElement('span');
    dot.dataset.mode = mode;
    dot.title = LABELS[mode];
    const fill = MODE_FALLBACK_COLORS[mode];
    const stroke = lighten(fill, STROKE_DARKEN);
    dot.style.cssText = [
      'display: inline-block',
      'width: 8px',
      'height: 8px',
      'border-radius: 50%',
      `background: ${fill}`,
      `border: 1px solid ${stroke}`,
      'cursor: pointer',
      'transition: opacity 150ms ease',
    ].join(';');
    dot.addEventListener('click', () => opts.onToggle(mode));
    container.appendChild(dot);
    dotByMode.set(mode, dot);
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

  function syncVisibility(): void {
    for (const [mode, dot] of dotByMode) {
      dot.style.opacity = opts.isVisible(mode) ? '1' : '0.3';
    }
  }

  document.body.appendChild(container);
  syncVisibility();

  return { element: container, syncVisibility };
}
