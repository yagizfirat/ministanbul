// Faz 6 KM1 alt-iş g — multi-route focus state (f-polish-5).
//
// Önce tek route_id idi; varyant gruplama (29B = 7 hat) sonrası grup
// header çift tıklama tüm variant'ları focus'a almalı, paint expression
// 'in literal' filter ile aynı anda parlar.
//
// Sözleşme:
//   null              → focus yok (default render)
//   readonly string[] → 1 veya N hat focused (tek-variant ve grup
//                        aynı interface ile çalışır)

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

  // Toggle: aynı set zaten focused ise null; değilse setFocus(routeIds).
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
