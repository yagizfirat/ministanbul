// Faz 6 KM1 alt-iş f-5 — sağ hat paneli.
//
// Mimari prensipler (kullanıcı kararı: panel ileride yer/boyut/davranış
// olarak değişebilir; kod buna hazır):
//   - Tüm magic number'lar RoutePanelConfig içinde, override'lanabilir
//   - DOM class isimli, CSS değişken kontrol noktalarıyla bağlı
//   - State (RouteVisibility) view'dan ayrı; panel sadece view
//   - 6 mod grup: metro/marmaray/tram/funicular/ferry/bus.
//     Bus grubu lazy: body open olunca virtual_list mount.
//
// Sınırlar:
//   - Drag/star/favori yok (Faz 6 KM5)
//   - Mobile bottom-sheet yok (Faz 6 KM2)
//   - Hat tıklamayla focus mode yok (alt-iş g)
//   - Search debounce yok (her keystroke ~2ms 9275 fuzzyMatch)

import './route_panel.css';
import type { RouteSummary } from '../data/api';
import type { RouteVisibility } from '../state/route_visibility';
import { fuzzyMatch } from '../util/turkish_normalize';
import { getRouteColor } from '../styling/route_colors';
import { createVirtualList, type VirtualListHandle } from './virtual_list';

export interface RoutePanelConfig {
  width: string;
  position: 'left' | 'right';
  collapseWidth: string;
  itemHeight: number;
  busVirtualizationOverscan: number;
}

const DEFAULT_CONFIG: RoutePanelConfig = {
  width: '340px',
  position: 'right',
  collapseWidth: '40px',
  itemHeight: 40,
  busVirtualizationOverscan: 5,
};

interface ModeRow {
  key: string;
  label: string;
}

const MODE_ORDER: ReadonlyArray<ModeRow> = [
  { key: 'metro', label: 'Metro' },
  { key: 'marmaray', label: 'Marmaray' },
  { key: 'tram', label: 'Tramvay' },
  { key: 'funicular', label: 'Füniküler' },
  { key: 'ferry', label: 'Vapur' },
  { key: 'bus', label: 'Otobüs' },
];

interface ModeGroupRefs {
  el: HTMLElement;
  header: HTMLElement;
  body: HTMLElement;
  countEl: HTMLElement;
  bulkBtn: HTMLElement;
  itemByRouteId: Map<string, HTMLElement>; // bus dışı modlar
  busListContainer?: HTMLElement;
  busLoadingEl?: HTMLElement;
  busErrorEl?: HTMLElement;
  virtualList?: VirtualListHandle<RouteSummary>;
}

export interface RoutePanelOptions {
  visibility: RouteVisibility;
  routes: RouteSummary[];
  // Reset butonunun döndüğü visible set. Genelde polyline + ferry
  // route_id'leri (bus default hidden — Mini Tokyo 3D paterni).
  defaultVisibleIds: readonly string[];
  config?: Partial<RoutePanelConfig>;
}

const HINT_TEXT =
  'Renkli noktalar tarife-bazlı simülasyondur, gerçek gecikme/aksaklık yansıtmaz.';

export interface RoutePanelHandle {
  element: HTMLElement;
  setRoutes(routes: RouteSummary[]): void;
  setBusLoading(loading: boolean): void;
  setBusError(message: string | null): void;
  destroy(): void;
}

export function createRoutePanel(opts: RoutePanelOptions): RoutePanelHandle {
  const config: RoutePanelConfig = { ...DEFAULT_CONFIG, ...opts.config };
  let allRoutes = opts.routes;
  let searchQuery = '';
  let collapsed = false;
  let busLoading = false;
  let busError: string | null = null;

  const root = document.createElement('div');
  root.className = 'route-panel';
  root.dataset.position = config.position;
  root.dataset.collapsed = 'false';
  root.style.setProperty('--route-panel-width', config.width);
  root.style.setProperty('--route-panel-collapse-width', config.collapseWidth);

  // ── header ────────────────────────────────────────────────────────
  // Çift satır: row1 (title + hint + collapse), row2 (count + bulk).
  const header = document.createElement('div');
  header.className = 'route-panel__header';

  const row1 = document.createElement('div');
  row1.className = 'route-panel__header-row1';
  const title = document.createElement('span');
  title.className = 'route-panel__title';
  title.textContent = 'Hatlar';
  const hintIcon = document.createElement('span');
  hintIcon.className = 'route-panel__hint-icon';
  hintIcon.textContent = '?';
  hintIcon.title = HINT_TEXT;
  const collapseBtn = document.createElement('button');
  collapseBtn.className = 'route-panel__collapse-btn';
  collapseBtn.textContent = config.position === 'right' ? '<' : '>';
  collapseBtn.addEventListener('click', () => toggleCollapse());
  row1.append(title, hintIcon, collapseBtn);

  const row2 = document.createElement('div');
  row2.className = 'route-panel__header-row2';
  const headerCount = document.createElement('span');
  headerCount.className = 'route-panel__count';
  const bulkActions = document.createElement('div');
  bulkActions.className = 'route-panel__bulk-actions';
  const allBtn = document.createElement('button');
  allBtn.textContent = 'Tümü';
  allBtn.addEventListener('click', () => onSelectAll());
  const noneBtn = document.createElement('button');
  noneBtn.textContent = 'Hiçbiri';
  noneBtn.addEventListener('click', () => onSelectNone());
  const resetBtn = document.createElement('button');
  resetBtn.textContent = 'Reset';
  resetBtn.addEventListener('click', () => onReset());
  bulkActions.append(allBtn, noneBtn, resetBtn);
  row2.append(headerCount, bulkActions);

  header.append(row1, row2);
  root.appendChild(header);

  // ── search ────────────────────────────────────────────────────────
  const searchEl = document.createElement('div');
  searchEl.className = 'route-panel__search';
  const searchInput = document.createElement('input');
  searchInput.type = 'text';
  searchInput.className = 'route-panel__search-input';
  searchInput.placeholder = 'Hat ara…';
  searchInput.addEventListener('input', () => onSearchInput(searchInput.value));
  const searchClear = document.createElement('button');
  searchClear.className = 'route-panel__search-clear';
  searchClear.textContent = '×';
  searchClear.addEventListener('click', () => {
    searchInput.value = '';
    onSearchInput('');
  });
  searchEl.append(searchInput, searchClear);
  root.appendChild(searchEl);

  // ── groups container ──────────────────────────────────────────────
  const groupsEl = document.createElement('div');
  groupsEl.className = 'route-panel__groups';
  root.appendChild(groupsEl);

  const groupsByMode = new Map<string, ModeGroupRefs>();
  for (const m of MODE_ORDER) {
    const refs = createModeGroup(m);
    groupsEl.appendChild(refs.el);
    groupsByMode.set(m.key, refs);
  }

  // İlk render + RouteVisibility değişimlerine subscribe.
  rebuildItems();
  applySearch();
  syncCheckboxes();
  updateHeaderCount();
  opts.visibility.subscribe(() => {
    syncCheckboxes();
    updateHeaderCount();
  });

  document.body.appendChild(root);

  // ──────────────────────────────────────────────────────────────────
  function createModeGroup(m: ModeRow): ModeGroupRefs {
    const el = document.createElement('div');
    el.className = 'route-panel__group';
    el.dataset.mode = m.key;
    // Bus default kapalı (lazy mount); diğerleri default açık.
    el.dataset.open = m.key === 'bus' ? 'false' : 'true';

    const headerEl = document.createElement('div');
    headerEl.className = 'route-panel__group-header';
    headerEl.addEventListener('click', (e) => {
      // Bulk butonu propagation'ı kesiyor — header click sadece toggle
      if (e.target instanceof HTMLElement && e.target.closest('.route-panel__group-bulk-btn')) {
        return;
      }
      toggleGroupOpen(m.key);
    });
    const toggle = document.createElement('button');
    toggle.className = 'route-panel__group-toggle';
    toggle.textContent = '▾';
    toggle.setAttribute('aria-label', 'Grup aç/kapat');
    const labelEl = document.createElement('span');
    labelEl.className = 'route-panel__group-label';
    labelEl.textContent = m.label;
    const countEl = document.createElement('span');
    countEl.className = 'route-panel__group-count';
    const bulkBtn = document.createElement('button');
    bulkBtn.className = 'route-panel__group-bulk-btn';
    bulkBtn.textContent = 'Tümü';
    bulkBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      onBulkToggle(m.key);
    });
    headerEl.append(toggle, labelEl, countEl, bulkBtn);

    const body = document.createElement('div');
    body.className = 'route-panel__group-body';

    el.append(headerEl, body);
    return {
      el,
      header: headerEl,
      body,
      countEl,
      bulkBtn,
      itemByRouteId: new Map(),
    };
  }

  function rebuildItems(): void {
    // Bus dışı modlar: DOM'da inline. Bus: lazy mount.
    for (const [modeKey, refs] of groupsByMode) {
      refs.body.replaceChildren();
      refs.itemByRouteId.clear();
      if (refs.virtualList) {
        refs.virtualList.destroy();
        refs.virtualList = undefined;
      }
      refs.busListContainer = undefined;
      refs.busLoadingEl = undefined;
      refs.busErrorEl = undefined;

      const modeRoutes = allRoutes.filter((r) => r.mode === modeKey);

      if (modeKey === 'bus') {
        // Loading/error placeholder (state'e göre setBusLoading/setBusError
        // çağrıları dolduracak).
        const loadingEl = document.createElement('div');
        loadingEl.className = 'route-panel__bus-loading';
        loadingEl.textContent = 'Otobüs hatları yükleniyor…';
        loadingEl.style.display = 'none';
        const errorEl = document.createElement('div');
        errorEl.className = 'route-panel__bus-error';
        errorEl.style.display = 'none';
        const listContainer = document.createElement('div');
        listContainer.className = 'route-panel__bus-list';
        refs.body.append(loadingEl, errorEl, listContainer);
        refs.busLoadingEl = loadingEl;
        refs.busErrorEl = errorEl;
        refs.busListContainer = listContainer;
        // Lazy mount: virtual_list sadece body open olduğunda yaratılır.
        if (refs.el.dataset.open === 'true') {
          mountBusVirtualList(refs);
        }
        applyBusStateVisibility(refs);
      } else {
        for (const route of modeRoutes) {
          const item = renderRouteItem(route);
          refs.body.appendChild(item);
          refs.itemByRouteId.set(route.route_id, item);
        }
      }
    }
    updateGroupCounts();
  }

  function mountBusVirtualList(refs: ModeGroupRefs): void {
    if (refs.virtualList || !refs.busListContainer) return;
    const busRoutes = currentVisibleBusRoutes();
    refs.virtualList = createVirtualList({
      container: refs.busListContainer,
      items: busRoutes,
      itemHeight: config.itemHeight,
      overscan: config.busVirtualizationOverscan,
      renderItem: (route) => renderRouteItem(route),
    });
  }

  function currentVisibleBusRoutes(): RouteSummary[] {
    const buses = allRoutes.filter((r) => r.mode === 'bus');
    if (searchQuery === '') return buses;
    return buses.filter(
      (r) => fuzzyMatch(searchQuery, r.short_name) || fuzzyMatch(searchQuery, r.long_name),
    );
  }

  function renderRouteItem(route: RouteSummary): HTMLElement {
    const el = document.createElement('div');
    el.className = 'route-panel__route-item';
    el.dataset.routeId = route.route_id;

    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.checked = opts.visibility.isVisible(route.route_id);
    cb.addEventListener('click', (e) => e.stopPropagation());
    cb.addEventListener('change', () => opts.visibility.toggle(route.route_id));

    const dot = document.createElement('span');
    dot.className = 'route-panel__route-color-dot';
    dot.style.background = getRouteColor(route.short_name, route.mode);

    const shortEl = document.createElement('span');
    shortEl.className = 'route-panel__route-short';
    shortEl.textContent = route.short_name;

    const longEl = document.createElement('span');
    longEl.className = 'route-panel__route-long';
    longEl.textContent = route.long_name;

    const operatorEl = document.createElement('span');
    operatorEl.className = 'route-panel__route-operator';
    operatorEl.textContent = route.agency_name || '';

    el.append(cb, dot, shortEl, longEl, operatorEl);
    el.addEventListener('click', () => {
      // Item gövdesine click → checkbox toggle (UX kolaylığı).
      cb.checked = !cb.checked;
      opts.visibility.toggle(route.route_id);
    });
    return el;
  }

  function onSearchInput(value: string): void {
    searchQuery = value;
    searchClear.dataset.visible = value ? 'true' : 'false';
    applySearch();
    updateGroupCounts();
  }

  function applySearch(): void {
    for (const [modeKey, refs] of groupsByMode) {
      if (modeKey === 'bus') {
        // virtual_list setItems
        if (refs.virtualList) {
          refs.virtualList.setItems(currentVisibleBusRoutes());
        }
        continue;
      }
      for (const [, item] of refs.itemByRouteId) {
        const routeId = item.dataset.routeId!;
        const route = allRoutes.find((r) => r.route_id === routeId);
        const match =
          !route ||
          searchQuery === '' ||
          fuzzyMatch(searchQuery, route.short_name) ||
          fuzzyMatch(searchQuery, route.long_name);
        item.dataset.hidden = match ? 'false' : 'true';
      }
    }
  }

  function syncCheckboxes(): void {
    for (const [modeKey, refs] of groupsByMode) {
      if (modeKey === 'bus') continue; // bus item'ları virtual_list ile, render anında okuyor
      for (const [routeId, item] of refs.itemByRouteId) {
        const cb = item.querySelector<HTMLInputElement>('input[type="checkbox"]');
        if (cb) cb.checked = opts.visibility.isVisible(routeId);
      }
    }
  }

  function updateGroupCounts(): void {
    for (const [modeKey, refs] of groupsByMode) {
      const routes = allRoutes.filter((r) => r.mode === modeKey);
      const total = routes.length;
      const filtered =
        searchQuery === ''
          ? total
          : routes.filter(
              (r) => fuzzyMatch(searchQuery, r.short_name) || fuzzyMatch(searchQuery, r.long_name),
            ).length;
      refs.countEl.textContent = searchQuery === '' ? `${total}` : `${filtered}/${total}`;
    }
  }

  function updateHeaderCount(): void {
    const visibleCount = opts.visibility.getVisible().size;
    headerCount.textContent = `${visibleCount} hat görünür`;
  }

  function toggleGroupOpen(modeKey: string): void {
    const refs = groupsByMode.get(modeKey);
    if (!refs) return;
    const wasOpen = refs.el.dataset.open === 'true';
    refs.el.dataset.open = wasOpen ? 'false' : 'true';
    if (modeKey === 'bus' && !wasOpen) {
      mountBusVirtualList(refs);
    }
  }

  function onBulkToggle(modeKey: string): void {
    const routes = allRoutes.filter((r) => r.mode === modeKey);
    const ids = routes.map((r) => r.route_id);
    const allVisible = ids.every((id) => opts.visibility.isVisible(id));
    opts.visibility.setBulkVisible(ids, !allVisible);
  }

  function onSelectAll(): void {
    const ids = allRoutes.map((r) => r.route_id);
    opts.visibility.setBulkVisible(ids, true);
  }

  function onSelectNone(): void {
    const ids = allRoutes.map((r) => r.route_id);
    opts.visibility.setBulkVisible(ids, false);
  }

  function onReset(): void {
    opts.visibility.resetToDefault(opts.defaultVisibleIds);
  }

  function toggleCollapse(): void {
    collapsed = !collapsed;
    root.dataset.collapsed = collapsed ? 'true' : 'false';
    collapseBtn.textContent = collapsed
      ? config.position === 'right'
        ? '>'
        : '<'
      : config.position === 'right'
        ? '<'
        : '>';
  }

  function applyBusStateVisibility(refs: ModeGroupRefs): void {
    if (!refs.busLoadingEl || !refs.busErrorEl || !refs.busListContainer) return;
    refs.busLoadingEl.style.display = busLoading ? 'block' : 'none';
    refs.busErrorEl.style.display = busError ? 'block' : 'none';
    refs.busErrorEl.textContent = busError ?? '';
    refs.busListContainer.style.display = busLoading || busError ? 'none' : 'block';
  }

  // ── public API ────────────────────────────────────────────────────
  return {
    element: root,

    setRoutes(routes: RouteSummary[]): void {
      allRoutes = routes;
      rebuildItems();
      applySearch();
      syncCheckboxes();
      updateHeaderCount();
    },

    setBusLoading(loading: boolean): void {
      busLoading = loading;
      const refs = groupsByMode.get('bus');
      if (refs) applyBusStateVisibility(refs);
    },

    setBusError(message: string | null): void {
      busError = message;
      const refs = groupsByMode.get('bus');
      if (refs) applyBusStateVisibility(refs);
    },

    destroy(): void {
      for (const refs of groupsByMode.values()) {
        if (refs.virtualList) refs.virtualList.destroy();
      }
      root.remove();
    },
  };
}
