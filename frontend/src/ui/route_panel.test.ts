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
  // KM5-e.2: bus route panel'de hiç render edilmemeli (mode 'bus' MODE_ORDER'da
  // yok, hat-bazlı kontrol iptal). Mevcut bırakıldı, panel sessizce filtreliyor.
  route({ id: 5, route_id: 'iett:29B', short_name: '29B', long_name: 'Şişhane – Hacıosman', mode: 'bus', agency_name: 'IETT' }),
];

const POLYLINE_VISIBLE = SAMPLE_ROUTES.filter((r) => r.mode !== 'bus').map((r) => r.route_id);

let panel: RoutePanelHandle | null = null;

afterEach(() => {
  panel?.destroy();
  panel = null;
  document.body.innerHTML = '';
});

function mount(routes = SAMPLE_ROUTES, opts: {
  config?: Parameters<typeof createRoutePanel>[0]['config'];
  onBusVisibilityChange?: (v: boolean) => void;
  onMetrobusVisibilityChange?: (v: boolean) => void;
} = {}): RoutePanelHandle {
  const allIds = routes.map((r) => r.route_id);
  const visible = routes.filter((r) => r.mode !== 'bus').map((r) => r.route_id);
  const rv = new RouteVisibility(allIds, visible);
  panel = createRoutePanel({
    visibility: rv,
    routes,
    defaultVisibleIds: visible,
    config: opts.config,
    onBusVisibilityChange: opts.onBusVisibilityChange,
    onMetrobusVisibilityChange: opts.onMetrobusVisibilityChange,
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

  it('does not render the "121 hat görünür" header count (KM5-e.2)', () => {
    mount();
    expect(document.querySelector('.route-panel__count')).toBeNull();
  });
});

// ── Mod grupları ────────────────────────────────────────────────────
describe('createRoutePanel — mode groups (KM5-e.2: 5 mod, bus kaldırıldı)', () => {
  it('renders 5 mode groups (bus mode removed)', () => {
    mount();
    const groups = document.querySelectorAll('.route-panel__group');
    expect(groups.length).toBe(5);
    const modes = Array.from(groups).map((g) => (g as HTMLElement).dataset.mode);
    expect(modes).toEqual(['metro', 'marmaray', 'tram', 'funicular', 'ferry']);
  });

  it('puts polyline-mode routes into normal DOM items', () => {
    mount();
    const metroGroup = document.querySelector('.route-panel__group[data-mode="metro"]') as HTMLElement;
    const items = metroGroup.querySelectorAll('.route-panel__route-item');
    expect(items.length).toBe(2); // M1A, M2
    const m2 = metroGroup.querySelector('[data-route-id="public:m2"]') as HTMLElement;
    expect(m2).not.toBeNull();
    expect(m2.querySelector('.route-panel__route-short')?.textContent).toBe('M2');
  });

  it('does not render any bus route in mode groups', () => {
    mount();
    expect(document.querySelector('[data-route-id="iett:29B"]')).toBeNull();
  });

  it('all 5 mode groups default open', () => {
    mount();
    const byMode = (m: string) =>
      document.querySelector(`.route-panel__group[data-mode="${m}"]`) as HTMLElement;
    expect(byMode('metro').dataset.open).toBe('true');
    expect(byMode('marmaray').dataset.open).toBe('true');
    expect(byMode('tram').dataset.open).toBe('true');
    expect(byMode('funicular').dataset.open).toBe('true');
    expect(byMode('ferry').dataset.open).toBe('true');
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
});

// ── Search ──────────────────────────────────────────────────────────
describe('createRoutePanel — search', () => {
  it('typing M2 removes M1A from the metro group DOM (flatten rebuild)', () => {
    mount();
    const input = document.querySelector('.route-panel__search-input') as HTMLInputElement;
    input.value = 'M2';
    input.dispatchEvent(new Event('input'));
    expect(document.querySelector('[data-route-id="public:m1a"]')).toBeNull();
    expect(document.querySelector('[data-route-id="public:m2"]')).not.toBeNull();
  });

  it('Turkish-aware search ("şiş" matches "Şişhane" — bus route filtered out of panel scope)', () => {
    mount();
    const input = document.querySelector('.route-panel__search-input') as HTMLInputElement;
    input.value = 'şiş';
    input.dispatchEvent(new Event('input'));
    // M2 (Hacıosman) eşleşmiyor; eski 29B ('Şişhane') artık bus mode'da
    // panel scope dışı — search hiçbir polyline route bulmaz.
    expect(document.querySelector('[data-route-id="public:m2"]')).toBeNull();
    expect(document.querySelector('[data-route-id="iett:29B"]')).toBeNull();
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
    expect(document.querySelector('[data-route-id="public:m1a"]')).not.toBeNull();
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

// ── KM5-e.2: bus toggle satırları ──────────────────────────────────
describe('createRoutePanel — İETT bus + Metrobüs toggles (KM5-e.2)', () => {
  it('renders two bus toggle rows in dedicated section', () => {
    mount();
    const section = document.querySelector('.route-panel__iett-bus-toggles') as HTMLElement;
    expect(section).not.toBeNull();
    const rows = section.querySelectorAll('.route-panel__bus-toggle');
    expect(rows.length).toBe(2);
    expect((rows[0] as HTMLElement).dataset.key).toBe('iett-bus');
    expect((rows[1] as HTMLElement).dataset.key).toBe('metrobus');
  });

  it('toggle labels are "İETT Otobüs" and "Metrobüs"', () => {
    mount();
    const labels = Array.from(
      document.querySelectorAll('.route-panel__bus-toggle-label'),
    ).map((el) => el.textContent);
    expect(labels).toEqual(['İETT Otobüs', 'Metrobüs']);
  });

  it('toggles default checked (busVisible + metrobusVisible = true)', () => {
    mount();
    const cbs = document.querySelectorAll<HTMLInputElement>(
      '.route-panel__bus-toggle input[type="checkbox"]',
    );
    expect(cbs[0].checked).toBe(true);
    expect(cbs[1].checked).toBe(true);
  });

  it('initial vehicle counts render as "(0 araç)"', () => {
    mount();
    const counts = Array.from(
      document.querySelectorAll('.route-panel__bus-toggle-count'),
    ).map((el) => el.textContent);
    expect(counts).toEqual(['(0 araç)', '(0 araç)']);
  });

  it('setVehicleCounts updates both rows', () => {
    const handle = mount();
    handle.setVehicleCounts({ bus: 6700, metrobus: 211 });
    const counts = Array.from(
      document.querySelectorAll('.route-panel__bus-toggle-count'),
    ).map((el) => el.textContent);
    expect(counts).toEqual(['(6700 araç)', '(211 araç)']);
  });

  it('clicking İETT Otobüs toggle fires onBusVisibilityChange(false), then (true)', () => {
    const onBus = vi.fn();
    mount(SAMPLE_ROUTES, { onBusVisibilityChange: onBus });
    const cb = document.querySelector<HTMLInputElement>(
      '.route-panel__bus-toggle[data-key="iett-bus"] input[type="checkbox"]',
    )!;
    cb.checked = false;
    cb.dispatchEvent(new Event('change'));
    expect(onBus).toHaveBeenCalledWith(false);
    cb.checked = true;
    cb.dispatchEvent(new Event('change'));
    expect(onBus).toHaveBeenLastCalledWith(true);
  });

  it('clicking Metrobüs toggle fires onMetrobusVisibilityChange independent of bus', () => {
    const onBus = vi.fn();
    const onMetrobus = vi.fn();
    mount(SAMPLE_ROUTES, {
      onBusVisibilityChange: onBus,
      onMetrobusVisibilityChange: onMetrobus,
    });
    const cb = document.querySelector<HTMLInputElement>(
      '.route-panel__bus-toggle[data-key="metrobus"] input[type="checkbox"]',
    )!;
    cb.checked = false;
    cb.dispatchEvent(new Event('change'));
    expect(onMetrobus).toHaveBeenCalledWith(false);
    expect(onBus).not.toHaveBeenCalled();
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
    expect(btn.textContent).toBe('<');
    btn.click();
    expect(btn.textContent).toBe('>');
  });

  it('starts in expanded state with data-collapsed="false"', () => {
    mount();
    const root = document.querySelector('.route-panel') as HTMLElement;
    expect(root.dataset.collapsed).toBe('false');
  });
});

// ── Destroy ─────────────────────────────────────────────────────────
describe('createRoutePanel — destroy', () => {
  it('removes the panel from the DOM', () => {
    const handle = mount();
    expect(document.querySelector('.route-panel')).not.toBeNull();
    handle.destroy();
    panel = null; // afterEach double-destroy guard
    expect(document.querySelector('.route-panel')).toBeNull();
  });
});

// ── Item interaction ───────────────────────────────────────────────
describe('createRoutePanel — item interaction', () => {
  it('dblclick on a route item invokes onRouteDoubleClick callback (alt-iş g)', () => {
    const onDbl = vi.fn();
    const allIds = SAMPLE_ROUTES.map((r) => r.route_id);
    const rv = new RouteVisibility(allIds, POLYLINE_VISIBLE);
    panel = createRoutePanel({
      visibility: rv,
      routes: SAMPLE_ROUTES,
      defaultVisibleIds: POLYLINE_VISIBLE,
      onRouteDoubleClick: onDbl,
    });
    const m2 = document.querySelector('[data-route-id="public:m2"]') as HTMLElement;
    m2.dispatchEvent(new MouseEvent('dblclick', { bubbles: true }));
    expect(onDbl).toHaveBeenCalledWith('public:m2');
  });

  it('checkbox change toggles RouteVisibility', () => {
    const allIds = SAMPLE_ROUTES.map((r) => r.route_id);
    const rv = new RouteVisibility(allIds, POLYLINE_VISIBLE);
    panel = createRoutePanel({
      visibility: rv,
      routes: SAMPLE_ROUTES,
      defaultVisibleIds: POLYLINE_VISIBLE,
    });
    expect(rv.isVisible('public:m2')).toBe(true);
    const cb = document.querySelector<HTMLInputElement>(
      '[data-route-id="public:m2"] input[type="checkbox"]',
    )!;
    cb.checked = false;
    cb.dispatchEvent(new Event('change'));
    expect(rv.isVisible('public:m2')).toBe(false);
  });
});

// ── Variant grouping ──────────────────────────────────────────────
describe('createRoutePanel — variant grouping', () => {
  it('shows a single group-header for two routes sharing short_name 29B', () => {
    const variants = [
      route({ id: 10, route_id: 'public:m2-A', short_name: 'M2', long_name: 'Yenikapı – Hacıosman' }),
      route({ id: 11, route_id: 'public:m2-B', short_name: 'M2', long_name: 'Hacıosman – Yenikapı' }),
    ];
    mount(variants);
    const headers = document.querySelectorAll('.route-panel__route-variant-header[data-short-name="M2"]');
    expect(headers.length).toBe(1);
  });

  it('clicking the variant header expands the body to show all variants with "Araç N" labels', () => {
    const variants = [
      route({ id: 10, route_id: 'public:m2-A', short_name: 'M2' }),
      route({ id: 11, route_id: 'public:m2-B', short_name: 'M2' }),
    ];
    mount(variants);
    const headerSel = '.route-panel__route-variant-header[data-short-name="M2"]';
    (document.querySelector(headerSel) as HTMLElement).click();
    // applySearch DOM rebuild eder; eski referans ölü, yeni element query
    const newHeader = document.querySelector(headerSel) as HTMLElement;
    expect(newHeader.dataset.open).toBe('true');
    const variantItems = document.querySelectorAll('.route-panel__route-item--variant');
    expect(variantItems.length).toBe(2);
  });

  it('variant header dblclick fires onVariantGroupDoubleClick with all variant ids', () => {
    const variants = [
      route({ id: 10, route_id: 'public:m2-A', short_name: 'M2' }),
      route({ id: 11, route_id: 'public:m2-B', short_name: 'M2' }),
    ];
    const onGrp = vi.fn();
    const allIds = variants.map((r) => r.route_id);
    const rv = new RouteVisibility(allIds, allIds);
    panel = createRoutePanel({
      visibility: rv,
      routes: variants,
      defaultVisibleIds: allIds,
      onVariantGroupDoubleClick: onGrp,
    });
    const header = document.querySelector(
      '.route-panel__route-variant-header[data-short-name="M2"]',
    ) as HTMLElement;
    header.dispatchEvent(new MouseEvent('dblclick', { bubbles: true }));
    expect(onGrp).toHaveBeenCalledWith(['public:m2-A', 'public:m2-B']);
  });

  it('variant header checkbox is indeterminate when only some variants are visible', () => {
    const variants = [
      route({ id: 10, route_id: 'public:m2-A', short_name: 'M2' }),
      route({ id: 11, route_id: 'public:m2-B', short_name: 'M2' }),
    ];
    const allIds = variants.map((r) => r.route_id);
    const rv = new RouteVisibility(allIds, ['public:m2-A']); // only A
    panel = createRoutePanel({
      visibility: rv,
      routes: variants,
      defaultVisibleIds: allIds,
    });
    const cb = document.querySelector<HTMLInputElement>(
      '.route-panel__route-variant-header[data-short-name="M2"] input[type="checkbox"]',
    )!;
    expect(cb.indeterminate).toBe(true);
  });

  it('search by long_name auto-expands the parent variant group', () => {
    const variants = [
      route({ id: 10, route_id: 'public:m2-A', short_name: 'M2', long_name: 'Yenikapı – Hacıosman' }),
      route({ id: 11, route_id: 'public:m2-B', short_name: 'M2', long_name: 'Hacıosman – Yenikapı' }),
    ];
    mount(variants);
    const input = document.querySelector('.route-panel__search-input') as HTMLInputElement;
    input.value = 'Hacıosman';
    input.dispatchEvent(new Event('input'));
    // header açık olmalı (auto-expand) → variantItems görünür
    const variantItems = document.querySelectorAll('.route-panel__route-item--variant');
    expect(variantItems.length).toBeGreaterThan(0);
  });
});

// ── Mojibake warning ─────────────────────────────────────────────
describe('createRoutePanel — mojibake warning', () => {
  it('renders a ⚠ icon next to a route whose long_name is mojibake', () => {
    const broken = [
      route({ id: 50, route_id: 'public:bad', short_name: 'X1', long_name: 'KÄ°RAZLITEPE - ARDA' }),
    ];
    mount(broken);
    const item = document.querySelector('[data-route-id="public:bad"]') as HTMLElement;
    expect(item.querySelector('.route-panel__route-mojibake-warn')).not.toBeNull();
  });

  it('does not render the warn icon for clean Turkish text', () => {
    const clean = [route({ id: 60, route_id: 'public:ok', short_name: 'X2', long_name: 'Yenikapı – Hacıosman' })];
    mount(clean);
    const item = document.querySelector('[data-route-id="public:ok"]') as HTMLElement;
    expect(item.querySelector('.route-panel__route-mojibake-warn')).toBeNull();
  });
});

// ── Header bulk actions + hint ─────────────────────────────────────
describe('createRoutePanel — header bulk actions + hint', () => {
  it('renders the hint icon with a tooltip in the header', () => {
    mount();
    const hint = document.querySelector('.route-panel__hint-icon') as HTMLElement;
    expect(hint).not.toBeNull();
    expect(hint.title.length).toBeGreaterThan(0);
  });

  it('renders three bulk action buttons (Tümü, Hiçbiri, Reset)', () => {
    mount();
    const btns = Array.from(
      document.querySelectorAll('.route-panel__bulk-actions button'),
    ).map((b) => b.textContent);
    expect(btns).toEqual(['Tümü', 'Hiçbiri', 'Reset']);
  });

  it('Tümü click marks every route visible', () => {
    const allIds = SAMPLE_ROUTES.map((r) => r.route_id);
    const rv = new RouteVisibility(allIds, []);
    panel = createRoutePanel({
      visibility: rv,
      routes: SAMPLE_ROUTES,
      defaultVisibleIds: POLYLINE_VISIBLE,
    });
    const tumuBtn = Array.from(
      document.querySelectorAll('.route-panel__bulk-actions button'),
    ).find((b) => b.textContent === 'Tümü') as HTMLElement;
    tumuBtn.click();
    for (const id of allIds) expect(rv.isVisible(id)).toBe(true);
  });

  it('Hiçbiri click hides every route', () => {
    const allIds = SAMPLE_ROUTES.map((r) => r.route_id);
    const rv = new RouteVisibility(allIds, allIds);
    panel = createRoutePanel({
      visibility: rv,
      routes: SAMPLE_ROUTES,
      defaultVisibleIds: POLYLINE_VISIBLE,
    });
    const hicbBtn = Array.from(
      document.querySelectorAll('.route-panel__bulk-actions button'),
    ).find((b) => b.textContent === 'Hiçbiri') as HTMLElement;
    hicbBtn.click();
    for (const id of allIds) expect(rv.isVisible(id)).toBe(false);
  });

  it('Reset returns to defaultVisibleIds even after Tümü', () => {
    const allIds = SAMPLE_ROUTES.map((r) => r.route_id);
    const rv = new RouteVisibility(allIds, POLYLINE_VISIBLE);
    panel = createRoutePanel({
      visibility: rv,
      routes: SAMPLE_ROUTES,
      defaultVisibleIds: POLYLINE_VISIBLE,
    });
    const findBtn = (text: string) =>
      Array.from(document.querySelectorAll('.route-panel__bulk-actions button')).find(
        (b) => b.textContent === text,
      ) as HTMLElement;
    findBtn('Tümü').click();
    findBtn('Reset').click();
    for (const id of POLYLINE_VISIBLE) expect(rv.isVisible(id)).toBe(true);
    expect(rv.isVisible('iett:29B')).toBe(false); // bus default hidden
  });
});
