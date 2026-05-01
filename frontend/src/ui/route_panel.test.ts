// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { createRoutePanel, type RoutePanelHandle } from './route_panel';
import { RouteVisibility } from '../state/route_visibility';
import type { RouteSummary } from '../data/api';

function route(over: Partial<RouteSummary> = {}): RouteSummary {
  return {
    id: 1,
    route_id: 'public:m2',
    short_name: 'M2',
    long_name: 'Yenikapı – Hacıosman',
    route_type: 1,
    route_type_label: 'Subway',
    agency_name: 'Metro İstanbul',
    mode: 'metro',
    ...over,
  };
}

const SAMPLE_ROUTES: RouteSummary[] = [
  route({ id: 1, route_id: 'public:m1a', short_name: 'M1A', long_name: 'Yenikapı – Atatürk Hav.' }),
  route({ id: 2, route_id: 'public:m2', short_name: 'M2', long_name: 'Yenikapı – Hacıosman' }),
  route({ id: 3, route_id: 'public:t1', short_name: 'T1', long_name: 'Kabataş – Bağcılar', mode: 'tram', agency_name: 'Metro İstanbul' }),
  route({ id: 4, route_id: 'public:marmaray', short_name: 'Marmaray', long_name: 'Gebze – Halkalı', mode: 'marmaray', agency_name: 'TCDD' }),
  route({ id: 5, route_id: 'iett:29B', short_name: '29B', long_name: 'Şişhane – Hacıosman', mode: 'bus', agency_name: 'IETT' }),
];

const POLYLINE_VISIBLE = SAMPLE_ROUTES.filter((r) => r.mode !== 'bus').map((r) => r.route_id);

// jsdom layout helper — virtual_list bus list'i için clientHeight gerek.
function setScrollMetrics(el: HTMLElement, viewportHeight: number, scrollTop = 0): void {
  Object.defineProperty(el, 'clientHeight', { value: viewportHeight, configurable: true });
  Object.defineProperty(el, 'scrollTop', { value: scrollTop, writable: true, configurable: true });
}

let panel: RoutePanelHandle | null = null;

afterEach(() => {
  panel?.destroy();
  panel = null;
  document.body.innerHTML = '';
});

function mount(routes = SAMPLE_ROUTES, opts: { config?: Parameters<typeof createRoutePanel>[0]['config'] } = {}): RoutePanelHandle {
  const allIds = routes.map((r) => r.route_id);
  const visible = routes.filter((r) => r.mode !== 'bus').map((r) => r.route_id);
  const rv = new RouteVisibility(allIds, visible);
  panel = createRoutePanel({
    visibility: rv,
    routes,
    defaultVisibleIds: visible,
    config: opts.config,
  });
  return panel;
}

// ── Yapı ────────────────────────────────────────────────────────────
describe('createRoutePanel — DOM structure', () => {
  it('creates a panel root with header, search, and groups containers', () => {
    mount();
    const root = document.querySelector('.route-panel') as HTMLElement;
    expect(root).not.toBeNull();
    expect(root.querySelector('.route-panel__header')).not.toBeNull();
    expect(root.querySelector('.route-panel__search')).not.toBeNull();
    expect(root.querySelector('.route-panel__groups')).not.toBeNull();
  });

  it('honors config.position="left"', () => {
    mount(SAMPLE_ROUTES, { config: { position: 'left' } });
    const root = document.querySelector('.route-panel') as HTMLElement;
    expect(root.dataset.position).toBe('left');
  });

  it('exposes config.width via CSS variable', () => {
    mount(SAMPLE_ROUTES, { config: { width: '400px' } });
    const root = document.querySelector('.route-panel') as HTMLElement;
    expect(root.style.getPropertyValue('--route-panel-width')).toBe('400px');
  });
});

// ── Mod grupları ────────────────────────────────────────────────────
describe('createRoutePanel — mode groups', () => {
  it('renders all 6 mode groups even when some are empty', () => {
    mount();
    const groups = document.querySelectorAll('.route-panel__group');
    expect(groups.length).toBe(6);
    const modes = Array.from(groups).map((g) => (g as HTMLElement).dataset.mode);
    expect(modes).toEqual(['metro', 'marmaray', 'tram', 'funicular', 'ferry', 'bus']);
  });

  it('puts polyline-mode routes (not bus) into normal DOM items', () => {
    mount();
    const metroGroup = document.querySelector('.route-panel__group[data-mode="metro"]') as HTMLElement;
    const items = metroGroup.querySelectorAll('.route-panel__route-item');
    expect(items.length).toBe(2); // M1A, M2
    const m2 = metroGroup.querySelector('[data-route-id="public:m2"]') as HTMLElement;
    expect(m2).not.toBeNull();
    expect(m2.querySelector('.route-panel__route-short')?.textContent).toBe('M2');
  });

  it('default open: every group except bus', () => {
    mount();
    const byMode = (m: string) =>
      document.querySelector(`.route-panel__group[data-mode="${m}"]`) as HTMLElement;
    expect(byMode('metro').dataset.open).toBe('true');
    expect(byMode('marmaray').dataset.open).toBe('true');
    expect(byMode('tram').dataset.open).toBe('true');
    expect(byMode('bus').dataset.open).toBe('false');
  });

  it('group header click toggles data-open', () => {
    mount();
    const metroGroup = document.querySelector('.route-panel__group[data-mode="metro"]') as HTMLElement;
    const headerEl = metroGroup.querySelector('.route-panel__group-header') as HTMLElement;
    headerEl.click();
    expect(metroGroup.dataset.open).toBe('false');
    headerEl.click();
    expect(metroGroup.dataset.open).toBe('true');
  });

  it('group bulk button click hides all routes in that mode (when all currently visible)', () => {
    const allIds = SAMPLE_ROUTES.map((r) => r.route_id);
    const rv = new RouteVisibility(allIds, POLYLINE_VISIBLE);
    panel = createRoutePanel({
      visibility: rv,
      routes: SAMPLE_ROUTES,
      defaultVisibleIds: POLYLINE_VISIBLE,
    });
    const metroGroup = document.querySelector('.route-panel__group[data-mode="metro"]') as HTMLElement;
    const bulk = metroGroup.querySelector('.route-panel__group-bulk-btn') as HTMLElement;
    bulk.click();
    expect(rv.isVisible('public:m1a')).toBe(false);
    expect(rv.isVisible('public:m2')).toBe(false);
    // Tram unaffected
    expect(rv.isVisible('public:t1')).toBe(true);
  });

  it('header count updates on visibility change', () => {
    const allIds = SAMPLE_ROUTES.map((r) => r.route_id);
    const rv = new RouteVisibility(allIds, POLYLINE_VISIBLE);
    panel = createRoutePanel({
      visibility: rv,
      routes: SAMPLE_ROUTES,
      defaultVisibleIds: POLYLINE_VISIBLE,
    });
    const headerCount = document.querySelector('.route-panel__count') as HTMLElement;
    const initialText = headerCount.textContent;
    rv.toggle('public:m2'); // hide M2
    expect(headerCount.textContent).not.toBe(initialText);
    expect(headerCount.textContent).toContain('3');
  });
});

// ── Search ──────────────────────────────────────────────────────────
describe('createRoutePanel — search', () => {
  it('typing M2 hides M1A in the metro group via data-hidden', () => {
    mount();
    const input = document.querySelector('.route-panel__search-input') as HTMLInputElement;
    input.value = 'M2';
    input.dispatchEvent(new Event('input'));
    const m1a = document.querySelector('[data-route-id="public:m1a"]') as HTMLElement;
    const m2 = document.querySelector('[data-route-id="public:m2"]') as HTMLElement;
    expect(m1a.dataset.hidden).toBe('true');
    expect(m2.dataset.hidden).toBe('false');
  });

  it('Turkish-aware search ("şiş" matches "Şişhane")', () => {
    mount();
    const input = document.querySelector('.route-panel__search-input') as HTMLInputElement;
    input.value = 'şiş';
    input.dispatchEvent(new Event('input'));
    // 29B (long_name "Şişhane – Hacıosman") is bus → no DOM item;
    // bus virtual_list is closed by default. We assert metro/tram aren't matched
    // and bus group count goes to 1/1.
    const m2 = document.querySelector('[data-route-id="public:m2"]') as HTMLElement;
    expect(m2.dataset.hidden).toBe('true');
    const busGroup = document.querySelector('.route-panel__group[data-mode="bus"]') as HTMLElement;
    const busCount = busGroup.querySelector('.route-panel__group-count')?.textContent;
    expect(busCount).toBe('1/1');
  });

  it('clear button empties the input and re-shows everything', () => {
    mount();
    const input = document.querySelector('.route-panel__search-input') as HTMLInputElement;
    input.value = 'M2';
    input.dispatchEvent(new Event('input'));
    const clearBtn = document.querySelector('.route-panel__search-clear') as HTMLElement;
    expect(clearBtn.dataset.visible).toBe('true');
    clearBtn.click();
    expect(input.value).toBe('');
    expect(clearBtn.dataset.visible).toBe('false');
    const m1a = document.querySelector('[data-route-id="public:m1a"]') as HTMLElement;
    expect(m1a.dataset.hidden).toBe('false');
  });

  it('group count shows filtered/total during active search', () => {
    mount();
    const input = document.querySelector('.route-panel__search-input') as HTMLInputElement;
    input.value = 'M2';
    input.dispatchEvent(new Event('input'));
    const metroCount = document.querySelector(
      '.route-panel__group[data-mode="metro"] .route-panel__group-count',
    )?.textContent;
    expect(metroCount).toBe('1/2');
  });
});

// ── Bus state ───────────────────────────────────────────────────────
describe('createRoutePanel — bus state (loading / error / list)', () => {
  it('setBusLoading shows a loading message', () => {
    const handle = mount();
    handle.setBusLoading(true);
    const loading = document.querySelector('.route-panel__bus-loading') as HTMLElement;
    expect(loading.style.display).toBe('block');
    handle.setBusLoading(false);
    expect(loading.style.display).toBe('none');
  });

  it('setBusError shows an error message and hides the list', () => {
    const handle = mount();
    handle.setBusError('Otobüs hatları yüklenemedi');
    const err = document.querySelector('.route-panel__bus-error') as HTMLElement;
    expect(err.style.display).toBe('block');
    expect(err.textContent).toBe('Otobüs hatları yüklenemedi');
    handle.setBusError(null);
    expect(err.style.display).toBe('none');
  });

  it('setRoutes rebuilds groups with new data (e.g. after bus fetch resolves)', () => {
    const handle = mount();
    const moreRoutes = [
      ...SAMPLE_ROUTES,
      route({ id: 6, route_id: 'iett:99', short_name: '99', long_name: 'X – Y', mode: 'bus', agency_name: 'IETT' }),
    ];
    handle.setRoutes(moreRoutes);
    const busGroup = document.querySelector('.route-panel__group[data-mode="bus"]') as HTMLElement;
    const busCount = busGroup.querySelector('.route-panel__group-count')?.textContent;
    expect(busCount).toBe('2');
  });

  it('opening the bus group mounts the virtual list (lazy)', () => {
    mount();
    const busGroup = document.querySelector('.route-panel__group[data-mode="bus"]') as HTMLElement;
    const listContainer = busGroup.querySelector('.route-panel__bus-list') as HTMLElement;
    setScrollMetrics(listContainer, 400);
    // Initially closed → virtual_list NOT mounted (no spacer).
    expect(listContainer.querySelector('.virtual-list__spacer')).toBeNull();
    const headerEl = busGroup.querySelector('.route-panel__group-header') as HTMLElement;
    headerEl.click(); // open
    expect(listContainer.querySelector('.virtual-list__spacer')).not.toBeNull();
  });
});

// ── Collapse ────────────────────────────────────────────────────────
describe('createRoutePanel — collapse', () => {
  it('collapse button toggles data-collapsed', () => {
    mount();
    const root = document.querySelector('.route-panel') as HTMLElement;
    expect(root.dataset.collapsed).toBe('false');
    const btn = document.querySelector('.route-panel__collapse-btn') as HTMLElement;
    btn.click();
    expect(root.dataset.collapsed).toBe('true');
    btn.click();
    expect(root.dataset.collapsed).toBe('false');
  });

  it('collapsed state keeps the collapse button reachable + flips its glyph', () => {
    mount(SAMPLE_ROUTES, { config: { position: 'right' } });
    const btn = document.querySelector('.route-panel__collapse-btn') as HTMLElement;
    expect(btn.textContent).toBe('<'); // initial (right side, expanded)
    btn.click();
    expect(btn.textContent).toBe('>'); // collapsed → re-open glyph
    expect(btn.isConnected).toBe(true); // still in DOM, click still works
    btn.click();
    expect(btn.textContent).toBe('<');
  });
});

// ── Destroy ─────────────────────────────────────────────────────────
describe('createRoutePanel — destroy', () => {
  it('removes the panel from the DOM', () => {
    const handle = mount();
    expect(document.querySelector('.route-panel')).not.toBeNull();
    handle.destroy();
    panel = null; // afterEach skip double destroy
    expect(document.querySelector('.route-panel')).toBeNull();
  });
});

// ── Item interaction ────────────────────────────────────────────────
describe('createRoutePanel — item interaction', () => {
  it('checkbox change toggles RouteVisibility', () => {
    const allIds = SAMPLE_ROUTES.map((r) => r.route_id);
    const rv = new RouteVisibility(allIds, POLYLINE_VISIBLE);
    const spy = vi.fn();
    rv.subscribe(spy);
    panel = createRoutePanel({
      visibility: rv,
      routes: SAMPLE_ROUTES,
      defaultVisibleIds: POLYLINE_VISIBLE,
    });
    const m2Item = document.querySelector('[data-route-id="public:m2"]') as HTMLElement;
    const cb = m2Item.querySelector('input[type="checkbox"]') as HTMLInputElement;
    cb.checked = false;
    cb.dispatchEvent(new Event('change'));
    expect(rv.isVisible('public:m2')).toBe(false);
    expect(spy).toHaveBeenCalled();
  });
});

// ── Header bulk actions + hint icon (KM1 alt-iş f-polish madde 4) ──
describe('createRoutePanel — header bulk actions + hint', () => {
  it('renders the hint icon with a tooltip in the header', () => {
    mount();
    const hint = document.querySelector('.route-panel__hint-icon') as HTMLElement;
    expect(hint).not.toBeNull();
    expect(hint.title).toMatch(/tarife-bazlı/i);
  });

  it('renders three bulk action buttons (Tümü, Hiçbiri, Reset)', () => {
    mount();
    const buttons = document.querySelectorAll<HTMLElement>(
      '.route-panel__bulk-actions button',
    );
    expect(buttons.length).toBe(3);
    const labels = Array.from(buttons).map((b) => b.textContent);
    expect(labels).toEqual(['Tümü', 'Hiçbiri', 'Reset']);
  });

  it('Tümü click marks every route visible', () => {
    const rv = new RouteVisibility(
      SAMPLE_ROUTES.map((r) => r.route_id),
      POLYLINE_VISIBLE, // bus hidden initially
    );
    panel = createRoutePanel({
      visibility: rv,
      routes: SAMPLE_ROUTES,
      defaultVisibleIds: POLYLINE_VISIBLE,
    });
    const allBtn = Array.from(
      document.querySelectorAll<HTMLElement>('.route-panel__bulk-actions button'),
    ).find((b) => b.textContent === 'Tümü')!;
    allBtn.click();
    expect(rv.isVisible('iett:29B')).toBe(true);
    expect(rv.isVisible('public:m2')).toBe(true);
  });

  it('Hiçbiri click hides every route', () => {
    const rv = new RouteVisibility(
      SAMPLE_ROUTES.map((r) => r.route_id),
      POLYLINE_VISIBLE,
    );
    panel = createRoutePanel({
      visibility: rv,
      routes: SAMPLE_ROUTES,
      defaultVisibleIds: POLYLINE_VISIBLE,
    });
    const noneBtn = Array.from(
      document.querySelectorAll<HTMLElement>('.route-panel__bulk-actions button'),
    ).find((b) => b.textContent === 'Hiçbiri')!;
    noneBtn.click();
    expect(rv.getVisible().size).toBe(0);
  });

  it('Reset returns to defaultVisibleIds even after Tümü', () => {
    const rv = new RouteVisibility(
      SAMPLE_ROUTES.map((r) => r.route_id),
      POLYLINE_VISIBLE,
    );
    panel = createRoutePanel({
      visibility: rv,
      routes: SAMPLE_ROUTES,
      defaultVisibleIds: POLYLINE_VISIBLE,
    });
    rv.setBulkVisible(SAMPLE_ROUTES.map((r) => r.route_id), true); // Tümü gibi
    expect(rv.isVisible('iett:29B')).toBe(true);
    const resetBtn = Array.from(
      document.querySelectorAll<HTMLElement>('.route-panel__bulk-actions button'),
    ).find((b) => b.textContent === 'Reset')!;
    resetBtn.click();
    expect(rv.isVisible('iett:29B')).toBe(false); // bus tekrar hidden
    expect(rv.isVisible('public:m2')).toBe(true); // polyline hâlâ visible
  });
});
