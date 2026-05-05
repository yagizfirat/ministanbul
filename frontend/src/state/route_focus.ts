// Multi-route focus state. A single route or a variant-group union
// (e.g. all variants sharing short_name "29B") share the same shape.
//   null              → no focus (default render)
//   readonly string[] → 1 or N routes focused

export type RouteFocusListener = (focused: readonly string[] | null) => void;

export class RouteFocus {
  private focused: readonly string[] | null = null;
  private listeners: RouteFocusListener[] = [];

  setFocus(routeIds: readonly string[] | null): void {
    if (this.equals(this.focused, routeIds)) return; // no-op
    this.focused = routeIds === null ? null : [...routeIds];
    for (const fn of this.listeners) fn(this.focused);
  }

  getFocused(): readonly string[] | null {
    return this.focused;
  }

  // Toggle: clears focus if the given set is already focused; otherwise
  // replaces the focus with it.
  toggle(routeIds: readonly string[]): void {
    if (this.equals(this.focused, routeIds)) {
      this.setFocus(null);
    } else {
      this.setFocus(routeIds);
    }
  }

  private equals(
    a: readonly string[] | null,
    b: readonly string[] | null,
  ): boolean {
    if (a === b) return true;
    if (a === null || b === null) return false;
    if (a.length !== b.length) return false;
    return a.every((id, i) => id === b[i]);
  }

  subscribe(fn: RouteFocusListener): void {
    this.listeners.push(fn);
  }
}
