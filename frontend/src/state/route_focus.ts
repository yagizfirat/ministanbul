// Faz 6 KM1 alt-iş g — tek hat focus state'i.
//
// route_visibility (görünür/gizli) ile orthogonal: tüm visible hatlar
// arasında BİR tane "focus" olabilir. Focus aktifken diğer visible
// hatlar opacity 0.2 ile sönük render edilir; focused hat parlak +
// glow halo ile vurgulanır ("ışın kılıcı" efekti).
//
// null = focus yok (default state, tüm visible hatlar normal renderda).

export type RouteFocusListener = (focused: string | null) => void;

export class RouteFocus {
  private focused: string | null = null;
  private listeners: RouteFocusListener[] = [];

  setFocus(routeId: string | null): void {
    if (this.focused === routeId) return; // no-op — listener tetiklenmez
    this.focused = routeId;
    for (const fn of this.listeners) fn(this.focused);
  }

  getFocused(): string | null {
    return this.focused;
  }

  // Aynı hat tekrar tıklanırsa focus'u kapat; başka hat → o hatta geç.
  toggle(routeId: string): void {
    this.setFocus(this.focused === routeId ? null : routeId);
  }

  subscribe(fn: RouteFocusListener): void {
    this.listeners.push(fn);
  }
}
