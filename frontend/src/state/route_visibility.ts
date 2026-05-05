// Visibility state behind the panel's route checkboxes. Listeners
// (typically a debounced applyFilters in main.ts) translate this set
// into MapLibre setFilter calls on route-lines and scheduled-circles.
// The fire() snapshot copies the set so listeners can't observe a
// mutation race.

export type RouteVisibilityListener = (visible: ReadonlySet<string>) => void;

export class RouteVisibility {
  private readonly visible: Set<string>;
  private readonly listeners: RouteVisibilityListener[] = [];
  // Total count of known route_ids; getFilterExpression compares it
  // against visible.size to short-circuit to a no-op filter when all
  // routes are visible.
  private totalCount: number;

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

  // Single fire() for the whole batch — toggling a mode group with
  // hundreds of routes shouldn't fire hundreds of listener calls.
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

  // Adds new (default-hidden) route_ids to totalCount without firing —
  // visible Set is unchanged, only the "all visible?" predicate
  // denominator grows.
  expandTotalCount(addedCount: number): void {
    this.totalCount += addedCount;
  }

  // No-op (and no fire) if the visible set already equals defaultIds.
  resetToDefault(defaultIds: readonly string[]): void {
    if (defaultIds.length === this.visible.size) {
      let allMatch = true;
      for (const id of defaultIds) {
        if (!this.visible.has(id)) {
          allMatch = false;
          break;
        }
      }
      if (allMatch) return;
    }
    this.visible.clear();
    for (const id of defaultIds) this.visible.add(id);
    this.fire();
  }

  subscribe(fn: RouteVisibilityListener): void {
    this.listeners.push(fn);
  }

  private fire(): void {
    const snapshot: ReadonlySet<string> = new Set(this.visible);
    for (const fn of this.listeners) fn(snapshot);
  }
}

// Returns the MapLibre filter for the current visibility set:
//   empty set → FILTER_NEVER (hide everything)
//   all visible → null (no filter, fast path)
//   otherwise   → ['in', ['get', 'route_id'], ['literal', ids]]
type Filter = unknown;

export const FILTER_NEVER: Filter = ['==', ['get', 'route_id'], '__none__'];

export function getFilterExpression(
  visible: ReadonlySet<string>,
  totalCount: number,
): Filter {
  if (visible.size === 0) return FILTER_NEVER;
  if (visible.size === totalCount) return null;
  return ['in', ['get', 'route_id'], ['literal', Array.from(visible)]];
}
