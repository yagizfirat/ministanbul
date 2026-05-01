// Faz 6 KM1 alt-iş e — scheduled vehicle mod görünürlük state'i.
// Chip click'i bu state'i toggle eder; listener MapLibre setFilter
// çağrısını main.ts içinden tetikler.

export type ModeKey = 'metro' | 'marmaray' | 'tram' | 'funicular' | 'ferry';

export const ALL_MODES: readonly ModeKey[] = [
  'metro',
  'marmaray',
  'tram',
  'funicular',
  'ferry',
] as const;

export type ModeVisibilityListener = (visible: ReadonlySet<ModeKey>) => void;

export class ModeVisibility {
  private readonly visible: Set<ModeKey> = new Set(ALL_MODES);
  private readonly listeners: ModeVisibilityListener[] = [];

  isVisible(mode: ModeKey): boolean {
    return this.visible.has(mode);
  }

  toggle(mode: ModeKey): void {
    if (this.visible.has(mode)) this.visible.delete(mode);
    else this.visible.add(mode);
    // Snapshot the set so each listener invocation is independent —
    // otherwise spies/recorders see the live mutating reference.
    const snapshot: ReadonlySet<ModeKey> = new Set(this.visible);
    for (const fn of this.listeners) fn(snapshot);
  }

  getVisible(): ReadonlySet<ModeKey> {
    return this.visible;
  }

  subscribe(fn: ModeVisibilityListener): void {
    this.listeners.push(fn);
  }
}

// MapLibre filter expression. Tip annotasyonu unknown — caller (main.ts)
// map.setFilter çağrısında MapLibre kendi cast'ini yapar, biz buradan
// FilterSpecification'a sıkı tip vermek istemiyoruz (maplibre-gl tip
// importları test ortamında ekstra footprint).
type Filter = unknown;

export const FILTER_NEVER: Filter = ['==', ['get', 'mode'], '__none__'];

export function getFilterExpression(visible: ReadonlySet<ModeKey>): Filter {
  if (visible.size === 0) return FILTER_NEVER;
  if (visible.size === ALL_MODES.length) return null; // no-op: tüm feature'lar geçer
  return ['in', ['get', 'mode'], ['literal', Array.from(visible)]];
}
