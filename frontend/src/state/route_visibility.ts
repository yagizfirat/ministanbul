// Faz 6 KM1 alt-iş f — sağ hat panelinin görünürlük state'i.
// Panel hat checkbox'ı bu state'i toggle eder; listener composite
// filter üzerinden 3 layer'a (route-lines, scheduled-circles,
// fleet-circles) MapLibre setFilter çağrısı tetikler.
//
// mode_visibility ile mimari simetri: snapshot listener (mutation
// race önler), ['in', 'literal'] filter, edge-case'ler için no-op
// (null) ve never-match expression.

export type RouteVisibilityListener = (visible: ReadonlySet<string>) => void;

export class RouteVisibility {
  private readonly visible: Set<string>;
  private readonly listeners: RouteVisibilityListener[] = [];
  // ALL_ROUTES — tüm route_id'lerin sayısı; getFilterExpression'ın
  // "tümü visible → null" karar noktası için bilinmesi şart.
  private readonly totalCount: number;

  constructor(allRouteIds: readonly string[], initiallyVisible: readonly string[]) {
    this.totalCount = allRouteIds.length;
    this.visible = new Set(initiallyVisible);
  }

  isVisible(routeId: string): boolean {
    return this.visible.has(routeId);
  }

  toggle(routeId: string): void {
    if (this.visible.has(routeId)) this.visible.delete(routeId);
    else this.visible.add(routeId);
    this.fire();
  }

  setVisible(routeId: string, visible: boolean): void {
    const has = this.visible.has(routeId);
    if (visible && !has) this.visible.add(routeId);
    else if (!visible && has) this.visible.delete(routeId);
    else return;
    this.fire();
  }

  // Tek bir snapshot+fire — mod grup checkbox'ı 9275 bus hattını
  // tek seferde toggle ederken 9275 listener tetiklemesini önler.
  setBulkVisible(routeIds: readonly string[], visible: boolean): void {
    let changed = false;
    for (const id of routeIds) {
      const has = this.visible.has(id);
      if (visible && !has) {
        this.visible.add(id);
        changed = true;
      } else if (!visible && has) {
        this.visible.delete(id);
        changed = true;
      }
    }
    if (changed) this.fire();
  }

  getVisible(): ReadonlySet<string> {
    return this.visible;
  }

  getTotalCount(): number {
    return this.totalCount;
  }

  subscribe(fn: RouteVisibilityListener): void {
    this.listeners.push(fn);
  }

  private fire(): void {
    const snapshot: ReadonlySet<string> = new Set(this.visible);
    for (const fn of this.listeners) fn(snapshot);
  }
}

// Filter expression — mode_visibility.getFilterExpression ile aynı
// API. Tip annotasyonu unknown — caller MapLibre cast'ini yapar.
type Filter = unknown;

export const FILTER_NEVER: Filter = ['==', ['get', 'route_id'], '__none__'];

export function getFilterExpression(
  visible: ReadonlySet<string>,
  totalCount: number,
): Filter {
  if (visible.size === 0) return FILTER_NEVER;
  if (visible.size === totalCount) return null; // no-op: tüm feature'lar geçer
  return ['in', ['get', 'route_id'], ['literal', Array.from(visible)]];
}
