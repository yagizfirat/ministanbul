// Right-side route panel.
//
// Architecture: magic numbers in RoutePanelConfig (overridable),
// DOM-class + CSS-variable bindings, RouteVisibility state separated
// from view. 5 mode groups (metro/marmaray/tram/funicular/ferry) plus
// two standalone toggles (İETT bus + metrobüs); İETT bus is filtered
// by vehicle.is_metrobus payload, not route_id (mapping disabled).

import './route_panel.css';
import type { RouteSummary } from '../data/api';
import type { RouteVisibility } from '../state/route_visibility';
import { fuzzyMatch, isMojibake } from '../util/turkish_normalize';
import { getRouteColor } from '../styling/route_colors';
import {
  expandedKey,
  flattenRoutesForDisplay,
  type FlatItem,
} from './route_panel_flatten';

export interface RoutePanelConfig {
  width: string;
  position: 'left' | 'right';
  collapseWidth: string;
  itemHeight: number;
}

const DEFAULT_CONFIG: RoutePanelConfig = {
  width: '400px',
  position: 'right',
  collapseWidth: '48px',
  itemHeight: 40,
};

interface ModeRow {
  key: string;
  label: string;
}

// İETT bus + metrobüs render as standalone toggle rows below MODE_ORDER.
const MODE_ORDER: ReadonlyArray<ModeRow> = [
  { key: 'metro', label: 'Metro' },
  { key: 'marmaray', label: 'Marmaray' },
  { key: 'tram', label: 'Tramvay' },
  { key: 'funicular', label: 'Füniküler' },
  { key: 'ferry', label: 'Vapur' },
];

interface ModeGroupRefs {
  el: HTMLElement;
  header: HTMLElement;
  body: HTMLElement;
  countEl: HTMLElement;
  bulkBtn: HTMLElement;
  // flatten sonrası DOM'da satır referansları
  // (single → route_id key, group-header → `header|${shortName}` key,
  //  group-variant → route_id key).
  itemByKey: Map<string, HTMLElement>;
}

interface BusToggleRefs {
  el: HTMLElement;
  checkbox: HTMLInputElement;
  countEl: HTMLElement;
}

export interface RoutePanelOptions {
  visibility: RouteVisibility;
  routes: RouteSummary[];
  // Reset target: typically polyline + ferry route_ids (bus default hidden).
  defaultVisibleIds: readonly string[];
  onRouteDoubleClick?: (routeId: string) => void;
  // Variant header double-click → focus the union of all variants.
  onVariantGroupDoubleClick?: (routeIds: readonly string[]) => void;
  onBusVisibilityChange?: (visible: boolean) => void;
  onMetrobusVisibilityChange?: (visible: boolean) => void;
  // Tümü → allOn=true, Hiçbiri → allOn=false. Caller propagates to
  // bus/metrobüs filter and routeFocus.
  onSelectAllChange?: (allOn: boolean) => void;
  onResetRequested?: () => void;
  config?: Partial<RoutePanelConfig>;
}

const HINT_TEXT =
  'Renkli noktalar tarife-bazlı simülasyondur, gerçek gecikme/aksaklık yansıtmaz.';

export interface RoutePanelHandle {
  element: HTMLElement;
  setRoutes(routes: RouteSummary[]): void;
  // Latest snapshot vehicle counts; passed by caller after snapshot push.
  setVehicleCounts(counts: { bus: number; metrobus: number }): void;
  // Atomic checkbox + internal-state sync; does NOT fire
  // onBus/MetrobusVisibilityChange callbacks (loop guard).
  setFleetVisibility(state: { bus: boolean; metrobus: boolean }): void;
  // null clears the focus highlight; otherwise marks matching rows and
  // their variant-group header with data-focused="true".
  setFocusedRoutes(focused: readonly string[] | null): void;
  destroy(): void;
}

export function createRoutePanel(opts: RoutePanelOptions): RoutePanelHandle {
  const config: RoutePanelConfig = { ...DEFAULT_CONFIG, ...opts.config };
  let allRoutes = opts.routes;
  let searchQuery = '';
  let collapsed = false;
  // KM5-e.2: iki bağımsız toggle, default ikisi açık. Mapping retire
  // kararıyla (KM5-a) hat-bazlı kontrol İETT bus için anlamsız;
  // is_metrobus payload field'ına göre fleet_layer filter güncellenir.
  let busVisible = true;
  let metrobusVisible = true;
  let vehicleCounts = { bus: 0, metrobus: 0 };
  // Re-applied after every DOM rebuild; Set used for O(1) row lookup.
  let focusedSet: Set<string> = new Set();
  // Open/closed state per variant group, keyed `${mode}|${shortName}`.
  const expandedGroups = new Set<string>();

  const root = document.createElement('div');
  root.className = 'route-panel';
  root.dataset.position = config.position;
  root.dataset.collapsed = 'false';
  // Default closed; meaningful only in the <=768px bottom-sheet layout.
  root.dataset.mobileOpen = 'false';
  root.style.setProperty('--route-panel-width', config.width);
  root.style.setProperty('--route-panel-collapse-width', config.collapseWidth);

  // Visible only on mobile (CSS-controlled).
  const dragHandle = document.createElement('div');
  dragHandle.className = 'route-panel__drag-handle';
  root.appendChild(dragHandle);

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

  // Bulk actions apply only to rail/ferry (the route_id-based scope);
  // bus/metrobüs are toggled via their dedicated rows.
  const row2 = document.createElement('div');
  row2.className = 'route-panel__header-row2';
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
  row2.append(bulkActions);

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

  // İETT bus + metrobüs toggle rows, rendered below the mode groups.
  const busTogglesEl = document.createElement('div');
  busTogglesEl.className = 'route-panel__iett-bus-toggles';
  const busToggleRef = createBusToggleRow({
    key: 'iett-bus',
    label: 'İETT Otobüs',
    iconColor: '#FFD200',
    initialChecked: busVisible,
    onChange: (v) => {
      busVisible = v;
      opts.onBusVisibilityChange?.(v);
    },
  });
  const metrobusToggleRef = createBusToggleRow({
    key: 'metrobus',
    label: 'Metrobüs',
    iconColor: '#3A3D40',
    initialChecked: metrobusVisible,
    onChange: (v) => {
      metrobusVisible = v;
      opts.onMetrobusVisibilityChange?.(v);
    },
  });
  busTogglesEl.append(busToggleRef.el, metrobusToggleRef.el);
  root.appendChild(busTogglesEl);

  // İlk render + RouteVisibility değişimlerine subscribe.
  rebuildItems();
  applySearch();
  syncCheckboxes();
  applyFocusedClasses();
  refreshBusToggleCounts();
  opts.visibility.subscribe(() => {
    syncCheckboxes();
  });

  document.body.appendChild(root);

  // Hamburger + backdrop attach to body (siblings of panel) so the
  // hamburger stays mounted when the panel is closed/translated. Both
  // are hidden via CSS on desktop.
  const hamburger = document.createElement('button');
  hamburger.className = 'mobile-hamburger';
  hamburger.setAttribute('aria-label', 'Hatlar panelini aç/kapat');
  hamburger.textContent = '☰';
  hamburger.addEventListener('click', () => setMobileOpen(!mobileOpen));
  document.body.appendChild(hamburger);

  const backdrop = document.createElement('div');
  backdrop.className = 'mobile-backdrop';
  backdrop.dataset.visible = 'false';
  backdrop.addEventListener('click', () => setMobileOpen(false));
  document.body.appendChild(backdrop);

  let mobileOpen = false;
  function setMobileOpen(open: boolean): void {
    mobileOpen = open;
    root.dataset.mobileOpen = open ? 'true' : 'false';
    backdrop.dataset.visible = open ? 'true' : 'false';
  }

  // ──────────────────────────────────────────────────────────────────
  function createModeGroup(m: ModeRow): ModeGroupRefs {
    const el = document.createElement('div');
    el.className = 'route-panel__group';
    el.dataset.mode = m.key;
    // KM5-e.2: bus mode kaldırıldı; tüm modlar default açık.
    el.dataset.open = 'true';

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
      itemByKey: new Map(),
    };
  }

  function rebuildItems(): void {
    for (const [modeKey, refs] of groupsByMode) {
      refs.body.replaceChildren();
      refs.itemByKey.clear();
      const modeRoutes = allRoutes.filter((r) => r.mode === modeKey);
      const flatItems = flattenRoutesForDisplay(modeRoutes, expandedGroups, searchQuery);
      for (const item of flatItems) {
        const node = renderFlatItem(item);
        refs.body.appendChild(node);
        refs.itemByKey.set(flatItemKey(item), node);
      }
    }
    updateGroupCounts();
  }

  function flatItemKey(item: FlatItem): string {
    if (item.kind === 'group-header') return `header|${item.mode}|${item.shortName}`;
    return item.route.route_id;
  }

  function renderFlatItem(item: FlatItem): HTMLElement {
    if (item.kind === 'single') return renderRouteItem(item.route);
    if (item.kind === 'group-variant') {
      return renderVariantItem(item.route, item.displayLabel);
    }
    return renderVariantHeader(item.shortName, item.mode, item.variants);
  }

  // Variant rows show only checkbox + short label ("Araç N"); long_name
  // (often mojibake) and agency are hidden.
  function renderVariantItem(route: RouteSummary, displayLabel: string): HTMLElement {
    const el = document.createElement('div');
    el.className = 'route-panel__route-item route-panel__route-item--variant';
    el.dataset.routeId = route.route_id;

    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.checked = opts.visibility.isVisible(route.route_id);
    cb.addEventListener('click', (e) => e.stopPropagation());
    cb.addEventListener('change', () => opts.visibility.toggle(route.route_id));

    const label = document.createElement('span');
    label.className = 'route-panel__variant-label';
    label.textContent = displayLabel;

    el.append(cb, label);
    el.addEventListener('click', () => {
      cb.checked = !cb.checked;
      opts.visibility.toggle(route.route_id);
    });
    el.addEventListener('dblclick', (e) => {
      e.stopPropagation();
      opts.onRouteDoubleClick?.(route.route_id);
    });
    return el;
  }

  function renderVariantHeader(
    shortName: string,
    mode: string,
    variants: RouteSummary[],
  ): HTMLElement {
    const el = document.createElement('div');
    el.className = 'route-panel__route-variant-header';
    el.dataset.shortName = shortName;
    el.dataset.mode = mode;
    const isOpen = expandedGroups.has(expandedKey(mode, shortName));
    el.dataset.open = isOpen ? 'true' : 'false';

    const toggle = document.createElement('span');
    toggle.className = 'route-panel__route-variant-toggle';
    toggle.textContent = '▾';

    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.addEventListener('click', (e) => e.stopPropagation());
    const ids = variants.map((v) => v.route_id);
    const visibleCount = ids.filter((id) => opts.visibility.isVisible(id)).length;
    cb.checked = visibleCount === ids.length;
    cb.indeterminate = visibleCount > 0 && visibleCount < ids.length;
    cb.addEventListener('change', () => {
      const allVisible = ids.every((id) => opts.visibility.isVisible(id));
      opts.visibility.setBulkVisible(ids, !allVisible);
    });

    const dot = document.createElement('span');
    dot.className = 'route-panel__route-color-dot';
    dot.style.background = getRouteColor(shortName, mode);

    const shortEl = document.createElement('span');
    shortEl.className = 'route-panel__route-short';
    shortEl.textContent = shortName;

    const countEl = document.createElement('span');
    countEl.className = 'route-panel__route-variant-count';
    countEl.textContent = `(${variants.length})`;

    el.append(toggle, cb, dot, shortEl, countEl);
    el.addEventListener('click', () => onVariantToggle(mode, shortName));
    // Double-click focuses + bbox-zooms the union of all variants.
    el.addEventListener('dblclick', (e) => {
      e.stopPropagation();
      opts.onVariantGroupDoubleClick?.(ids);
    });
    return el;
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
    if (isMojibake(route.long_name)) {
      const warn = document.createElement('span');
      warn.className = 'route-panel__route-mojibake-warn';
      warn.textContent = '⚠ ';
      warn.title = "Bu hat adı GTFS feed'inde bozuk geliyor (kaynakta encoding sorunu)";
      longEl.appendChild(warn);
      longEl.appendChild(document.createTextNode(route.long_name));
    } else {
      longEl.textContent = route.long_name;
    }

    const operatorEl = document.createElement('span');
    operatorEl.className = 'route-panel__route-operator';
    operatorEl.textContent = route.agency_name || '';

    el.append(cb, dot, shortEl, longEl, operatorEl);
    // Click anywhere on the row toggles the checkbox.
    el.addEventListener('click', () => {
      cb.checked = !cb.checked;
      opts.visibility.toggle(route.route_id);
    });
    // Double-click focuses the route and bbox-zooms.
    el.addEventListener('dblclick', (e) => {
      e.stopPropagation();
      opts.onRouteDoubleClick?.(route.route_id);
    });
    return el;
  }

  function onSearchInput(value: string): void {
    searchQuery = value;
    searchClear.dataset.visible = value ? 'true' : 'false';
    applySearch();
    applyFocusedClasses();
    updateGroupCounts();
  }

  function applySearch(): void {
    for (const [modeKey, refs] of groupsByMode) {
      refs.body.replaceChildren();
      refs.itemByKey.clear();
      const modeRoutes = allRoutes.filter((r) => r.mode === modeKey);
      const flatItems = flattenRoutesForDisplay(modeRoutes, expandedGroups, searchQuery);
      for (const item of flatItems) {
        const node = renderFlatItem(item);
        refs.body.appendChild(node);
        refs.itemByKey.set(flatItemKey(item), node);
      }
    }
  }

  function onVariantToggle(mode: string, shortName: string): void {
    const key = expandedKey(mode, shortName);
    if (expandedGroups.has(key)) expandedGroups.delete(key);
    else expandedGroups.add(key);
    applySearch();
    applyFocusedClasses();
    updateGroupCounts();
  }

  // Marks rows currently in focus with data-focused="true". A variant
  // group header is highlighted when any of its variants is focused.
  function applyFocusedClasses(): void {
    for (const [, refs] of groupsByMode) {
      for (const node of refs.itemByKey.values()) {
        if (node.classList.contains('route-panel__route-variant-header')) {
          const shortName = node.dataset.shortName!;
          const mode = node.dataset.mode!;
          const variantIds = allRoutes
            .filter((r) => r.mode === mode && r.short_name === shortName)
            .map((v) => v.route_id);
          const isFocused = variantIds.some((id) => focusedSet.has(id));
          node.dataset.focused = isFocused ? 'true' : 'false';
        } else {
          const routeId = node.dataset.routeId!;
          node.dataset.focused = focusedSet.has(routeId) ? 'true' : 'false';
        }
      }
    }
  }

  function syncCheckboxes(): void {
    for (const [, refs] of groupsByMode) {
      for (const node of refs.itemByKey.values()) {
        const cb = node.querySelector<HTMLInputElement>('input[type="checkbox"]');
        if (!cb) continue;
        if (node.classList.contains('route-panel__route-variant-header')) {
          const shortName = node.dataset.shortName!;
          const mode = node.dataset.mode!;
          const variants = allRoutes.filter(
            (r) => r.mode === mode && r.short_name === shortName,
          );
          const ids = variants.map((v) => v.route_id);
          const visible = ids.filter((id) => opts.visibility.isVisible(id)).length;
          cb.checked = visible === ids.length;
          cb.indeterminate = visible > 0 && visible < ids.length;
        } else {
          // single veya group-variant route item
          const routeId = node.dataset.routeId!;
          cb.checked = opts.visibility.isVisible(routeId);
        }
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

  function toggleGroupOpen(modeKey: string): void {
    const refs = groupsByMode.get(modeKey);
    if (!refs) return;
    const wasOpen = refs.el.dataset.open === 'true';
    refs.el.dataset.open = wasOpen ? 'false' : 'true';
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
    opts.onSelectAllChange?.(true);
  }

  function onSelectNone(): void {
    const ids = allRoutes.map((r) => r.route_id);
    opts.visibility.setBulkVisible(ids, false);
    opts.onSelectAllChange?.(false);
  }

  function onReset(): void {
    opts.visibility.resetToDefault(opts.defaultVisibleIds);
    opts.onResetRequested?.();
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

  function createBusToggleRow(rowOpts: {
    key: string;
    label: string;
    iconColor: string;
    initialChecked: boolean;
    onChange: (visible: boolean) => void;
  }): BusToggleRefs {
    const el = document.createElement('div');
    el.className = 'route-panel__bus-toggle';
    el.dataset.key = rowOpts.key;

    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.checked = rowOpts.initialChecked;
    checkbox.addEventListener('click', (e) => e.stopPropagation());
    checkbox.addEventListener('change', () => {
      rowOpts.onChange(checkbox.checked);
    });

    const dot = document.createElement('span');
    dot.className = 'route-panel__route-color-dot';
    dot.style.background = rowOpts.iconColor;

    const labelEl = document.createElement('span');
    labelEl.className = 'route-panel__bus-toggle-label';
    labelEl.textContent = rowOpts.label;

    const countEl = document.createElement('span');
    countEl.className = 'route-panel__bus-toggle-count';
    countEl.textContent = '(0 araç)';

    el.append(checkbox, dot, labelEl, countEl);
    el.addEventListener('click', () => {
      checkbox.checked = !checkbox.checked;
      rowOpts.onChange(checkbox.checked);
    });
    return { el, checkbox, countEl };
  }

  function refreshBusToggleCounts(): void {
    busToggleRef.countEl.textContent = `(${vehicleCounts.bus} araç)`;
    metrobusToggleRef.countEl.textContent = `(${vehicleCounts.metrobus} araç)`;
  }

  // ── public API ────────────────────────────────────────────────────
  return {
    element: root,

    setRoutes(routes: RouteSummary[]): void {
      allRoutes = routes;
      rebuildItems();
      applySearch();
      syncCheckboxes();
      applyFocusedClasses();
    },

    setVehicleCounts(counts: { bus: number; metrobus: number }): void {
      vehicleCounts = counts;
      refreshBusToggleCounts();
    },

    setFleetVisibility(state: { bus: boolean; metrobus: boolean }): void {
      busVisible = state.bus;
      metrobusVisible = state.metrobus;
      busToggleRef.checkbox.checked = state.bus;
      metrobusToggleRef.checkbox.checked = state.metrobus;
    },

    setFocusedRoutes(focused: readonly string[] | null): void {
      focusedSet = focused === null ? new Set() : new Set(focused);
      applyFocusedClasses();
    },

    destroy(): void {
      root.remove();
      hamburger.remove();
      backdrop.remove();
    },
  };
}
