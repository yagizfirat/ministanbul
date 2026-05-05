import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { connectWebSocket, type VehicleSnapshot } from './data/websocket';
import {
  fetchActiveRoutes,
  fetchActiveTrips,
  fetchLiveVehicles,
  type RouteSummary,
} from './data/api';
import { SnapshotStore } from './state/snapshot_store';
import { RouteStore } from './state/route_store';
import { buildFleetFilter, buildFleetPaint, initFleetLayer, updateFleet } from './render/fleet_layer';
import { initBuildingsLayer } from './render/buildings_layer';
import {
  buildRouteLinePaint,
  getRoutesBBox,
  initRouteLinesLayer,
  setGlowFocus,
} from './render/route_lines_layer';
import {
  buildScheduledLayerPaint,
  initScheduledLayer,
  updateScheduled,
} from './render/scheduled_layer';
import { initTerrain } from './render/terrain';
import { ScheduledFleet } from './simulation/scheduled_fleet';
import type { InterpolatedScheduledTrip } from './simulation/scheduled_trip';
import {
  RouteVisibility,
  getFilterExpression as getRouteFilter,
} from './state/route_visibility';
import { RouteFocus } from './state/route_focus';
import { debounceFrame } from './state/frame_debouncer';
import { parseUrlState, serializeUrlState } from './state/url_state';
import { createLastUpdateIndicator } from './ui/last_update_indicator';
import { createRoutePanel, type RoutePanelHandle } from './ui/route_panel';
import { showToast } from './ui/toast';
import { showVehiclePopup } from './ui/vehicle_popup';

const ISTANBUL_CENTER: [number, number] = [29.00, 41.04];
const STYLE_URL = 'https://tiles.openfreemap.org/styles/bright';
const REST_FALLBACK_DELAY_MS = 5_000;
const REST_POLL_INTERVAL_MS = 60_000;

// Modes drawn as polylines on app load. Marmaray ships inside `subway`
// and is split out by short_name in api.ts. Ferry routes are listed in
// the panel without polylines; bus/metrobüs render only as live circles.
const ALWAYS_VISIBLE_MODES = ['subway', 'tram', 'funicular'];
const ROUTE_FETCH_BATCH = 10;
const SCHEDULED_POLL_INTERVAL_MS = 60_000;
const SCHEDULED_MODES = ['metro', 'marmaray', 'tram', 'funicular', 'ferry'] as const;

const store = new SnapshotStore();
const scheduledFleets = new Map<string, ScheduledFleet>(
  SCHEDULED_MODES.map((m) => [m, new ScheduledFleet()]),
);
const indicator = createLastUpdateIndicator();

// Module-level Intl.DateTimeFormat cache: avoid building one per frame.
const ISTANBUL_TIME_FMT = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'Europe/Istanbul',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
});

function nowSecondsIstanbul(): number {
  // formatToParts so we don't have to parse free-form string output.
  const parts = ISTANBUL_TIME_FMT.formatToParts(new Date());
  let h = 0;
  let m = 0;
  let s = 0;
  for (const p of parts) {
    if (p.type === 'hour') h = parseInt(p.value, 10);
    else if (p.type === 'minute') m = parseInt(p.value, 10);
    else if (p.type === 'second') s = parseInt(p.value, 10);
  }
  return h * 3600 + m * 60 + s;
}

const map = new maplibregl.Map({
  container: 'map',
  style: STYLE_URL,
  center: ISTANBUL_CENTER,
  zoom: 12,
  pitch: 45,
  bearing: -20,
  maxPitch: 75,
  minZoom: 9,
  maxZoom: 18,
});

map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'top-right');

const routeStore = new RouteStore(map);

map.on('load', () => {
  console.log('[map] loaded');
  initTerrain(map);
  initBuildingsLayer(map);
  initFleetLayer(map);
  // Insert route-lines BEFORE fleet-circles so vehicles render on top of lines.
  initRouteLinesLayer(map, 'fleet-circles');
  // Scheduled layer sits on top of fleet-circles (last → topmost).
  initScheduledLayer(map);
  startRenderLoop();
  startRealtime();
  void loadAlwaysVisibleRoutes().then(() => startScheduledPolling());
});

let routeVisibility: RouteVisibility | null = null;
let routePanel: RoutePanelHandle | null = null;
const routeFocus = new RouteFocus();

// Re-paints the three layers + glow filter when the focused set changes.
// `focused` is null (no focus) or one or more route_ids.
function applyFocusPaint(focused: readonly string[] | null): void {
  if (map.getLayer('route-lines')) {
    const p = buildRouteLinePaint(focused) as Record<string, unknown>;
    map.setPaintProperty('route-lines', 'line-opacity', p['line-opacity'] as never);
    map.setPaintProperty('route-lines', 'line-width', p['line-width'] as never);
  }
  if (map.getLayer('scheduled-circles')) {
    const p = buildScheduledLayerPaint(focused) as Record<string, unknown>;
    map.setPaintProperty(
      'scheduled-circles',
      'circle-opacity',
      (p['circle-opacity'] ?? 1) as never,
    );
    map.setPaintProperty(
      'scheduled-circles',
      'circle-stroke-opacity',
      (p['circle-stroke-opacity'] ?? 1) as never,
    );
  }
  if (map.getLayer('fleet-circles')) {
    const p = buildFleetPaint(focused) as Record<string, unknown>;
    map.setPaintProperty(
      'fleet-circles',
      'circle-opacity',
      (p['circle-opacity'] ?? 1) as never,
    );
    map.setPaintProperty(
      'fleet-circles',
      'circle-stroke-opacity',
      (p['circle-stroke-opacity'] ?? 1) as never,
    );
  }
  setGlowFocus(map, focused);
}

async function loadAlwaysVisibleRoutes(): Promise<void> {
  console.log(`[routes] discovering active routes for ${ALWAYS_VISIBLE_MODES.length} modes...`);
  let polylineSummaries: RouteSummary[];
  try {
    polylineSummaries = await fetchActiveRoutes(ALWAYS_VISIBLE_MODES);
  } catch (err) {
    console.warn('[routes] discovery failed', err);
    return;
  }
  routeStore.registerSummaries(polylineSummaries);
  console.log(`[routes] found ${polylineSummaries.length} routes, loading shapes...`);

  let loaded = 0;
  let skipped = 0;
  for (let i = 0; i < polylineSummaries.length; i += ROUTE_FETCH_BATCH) {
    const batch = polylineSummaries.slice(i, i + ROUTE_FETCH_BATCH);
    const results = await Promise.allSettled(
      batch.map(async (s) => ({ s, outcome: await routeStore.add(s.route_id) })),
    );
    for (const r of results) {
      if (r.status === 'rejected') {
        console.warn('[routes] add failed', r.reason);
        continue;
      }
      const { s, outcome } = r.value;
      if (outcome === 'added') {
        loaded++;
        console.log(`[routes] ${s.short_name} (${s.long_name}) loaded`);
      } else if (outcome === 'no-shape') {
        skipped++;
        console.log(`[routes] ${s.short_name} skipped (no shape)`);
      }
    }
  }
  console.log(`[routes] all done: ${loaded} loaded, ${skipped} skipped`);

  // Ferry routes are listed in the panel without polylines (Şehir
  // Hatları geometry not in the public feed). They still need
  // RouteStore registration so vehicle popups can resolve their metadata.
  let ferrySummaries: RouteSummary[] = [];
  try {
    ferrySummaries = await fetchActiveRoutes(['ferry']);
    console.log(`[routes] ferry metadata for panel: ${ferrySummaries.length}`);
  } catch (err) {
    console.warn('[routes] ferry fetch failed', err);
  }
  routeStore.registerSummaries(ferrySummaries);

  const initialRoutes = [...polylineSummaries, ...ferrySummaries];
  const initialIds = initialRoutes.map((r) => r.route_id);
  // Restore visibility/fleet/focus state from `?routes=...&bus=off&...`;
  // unknown route_ids (stale share-links) are filtered out silently.
  const urlState = parseUrlState(window.location.search);
  const initialIdSet = new Set(initialIds);
  const filteredUrlRoutes = urlState.routes?.filter((id) => initialIdSet.has(id));
  const initiallyVisible = filteredUrlRoutes ?? initialIds;
  routeVisibility = new RouteVisibility(initialIds, initiallyVisible);
  let busVisible = urlState.bus ?? true;
  let metrobusVisible = urlState.metrobus ?? true;
  if (urlState.focus) {
    const validFocus = urlState.focus.filter((id) => initialIdSet.has(id));
    if (validFocus.length > 0) routeFocus.setFocus(validFocus);
  }
  function applyFleetVisibilityFilter(): void {
    if (!map.getLayer('fleet-circles')) return;
    map.setFilter(
      'fleet-circles',
      buildFleetFilter(busVisible, metrobusVisible) as never,
    );
  }
  // Debounce the setFilter chain so Reset/Select-All/rapid toggles
  // collapse into a single MapLibre style invalidation.
  const debouncedApplyFleet = debounceFrame(applyFleetVisibilityFilter);
  // Header bulk actions (Tümü/Hiçbiri/Reset) propagate to all three
  // visibility channels: route_id set, bus/metrobüs filter, and routeFocus.
  function applyFleetState(bus: boolean, metrobus: boolean): void {
    busVisible = bus;
    metrobusVisible = metrobus;
    debouncedApplyFleet();
    routePanel?.setFleetVisibility({ bus, metrobus });
    routeFocus.setFocus(null);
    // setFocus(null) is a no-op when focus is already null, so push
    // the URL update explicitly to capture the bus/metrobüs change.
    debouncedUpdateUrl();
  }
  // history.replaceState (not pushState) avoids polluting the browser
  // back-stack on every checkbox flip.
  function updateUrl(): void {
    if (!routeVisibility) return;
    const search = serializeUrlState(
      {
        routes: Array.from(routeVisibility.getVisible()),
        bus: busVisible,
        metrobus: metrobusVisible,
        focus: routeFocus.getFocused(),
      },
      { routes: initialIds, bus: true, metrobus: true, focus: null },
    );
    const next = search === '' ? window.location.pathname : search;
    history.replaceState({}, '', next);
  }
  const debouncedUpdateUrl = debounceFrame(updateUrl);
  routeVisibility.subscribe(() => debouncedUpdateUrl());
  routeFocus.subscribe(() => debouncedUpdateUrl());
  routePanel = createRoutePanel({
    visibility: routeVisibility,
    routes: initialRoutes,
    defaultVisibleIds: initialIds, // Reset hedefi (polyline + ferry)
    onRouteDoubleClick: (routeId) => focusAndZoom([routeId]),
    onVariantGroupDoubleClick: (routeIds) => focusAndZoom(routeIds),
    onBusVisibilityChange: (v) => {
      busVisible = v;
      debouncedApplyFleet();
      debouncedUpdateUrl();
    },
    onMetrobusVisibilityChange: (v) => {
      metrobusVisible = v;
      debouncedApplyFleet();
      debouncedUpdateUrl();
    },
    onSelectAllChange: (allOn) => applyFleetState(allOn, allOn),
    onResetRequested: () => applyFleetState(true, true),
  });

  function focusAndZoom(routeIds: readonly string[]): void {
    routeFocus.setFocus(routeIds);
    // Bbox lookup chain:
    //   1. polyline modes (metro/marmaray/tram/funicular)
    //   2. SnapshotStore — live İETT vehicle positions
    //   3. ScheduledFleet — active prepared trips (covers ferry, which
    //      has no polyline; falls through here only)
    let bbox = getRoutesBBox(routeIds) ?? store.getVehicleBBoxForRoutes(routeIds);
    if (bbox === null) {
      for (const fleet of scheduledFleets.values()) {
        bbox = fleet.getRoutesBBox(routeIds);
        if (bbox !== null) break;
      }
    }
    if (bbox) {
      map.fitBounds(bbox as [number, number, number, number], { padding: 80 });
    } else {
      showToast('Bu hatta şu an aktif araç yok, zoom yapılamadı');
    }
  }

  routeFocus.subscribe(applyFocusPaint);
  routeFocus.subscribe((focused) => routePanel?.setFocusedRoutes(focused));

  // Polyline click focuses the route; clicks on empty map area reset focus.
  map.on('click', 'route-lines', (e) => {
    const rid = e.features?.[0]?.properties?.route_id as string | undefined;
    if (rid) routeFocus.setFocus([rid]);
  });
  map.on('click', 'fleet-circles', (e) => {
    if (!e.features?.[0]) return;
    showVehiclePopup(map, e.lngLat, e.features[0].properties as never, 'iett', routeStore);
  });
  map.on('click', 'scheduled-circles', (e) => {
    if (!e.features?.[0]) return;
    const props = e.features[0].properties as { trip_id?: string; mode?: string };
    // Pass PreparedTrip + nowSec for the rich popup variant; missing
    // fleet/trip_id falls through to a meta-only popup gracefully.
    const fleet = props.mode ? scheduledFleets.get(props.mode) : undefined;
    const prepared = (fleet && props.trip_id)
      ? fleet.getPreparedTrip(props.trip_id)
      : null;
    showVehiclePopup(
      map,
      e.lngLat,
      e.features[0].properties as never,
      'scheduled',
      routeStore,
      { nowSec: nowSecondsIstanbul(), prepared },
    );
  });
  map.on('click', (e) => {
    // Empty-area click resets focus (layer-specific handlers above
    // handle the non-empty cases).
    const hits = map.queryRenderedFeatures(e.point, {
      layers: ['route-lines', 'fleet-circles', 'scheduled-circles'],
    });
    if (hits.length === 0) routeFocus.setFocus(null);
  });

  function applyFilters(): void {
    if (!routeVisibility) return;
    const routeF = getRouteFilter(routeVisibility.getVisible(), routeVisibility.getTotalCount());
    if (map.getLayer('route-lines')) {
      map.setFilter('route-lines', routeF as never);
    }
    if (map.getLayer('scheduled-circles')) {
      map.setFilter('scheduled-circles', routeF as never);
    }
    // fleet-circles is intentionally not touched here — it has its own
    // single-channel filter in applyFleetVisibilityFilter (bus/metrobüs
    // payload, not route_id).
  }
  // RAF debounce: Reset/Select-All collapse N subscribe fires into one.
  const debouncedApplyFilters = debounceFrame(applyFilters);
  routeVisibility.subscribe(debouncedApplyFilters);
  applyFilters();
  applyFleetVisibilityFilter();
}

function startRenderLoop(): void {
  // Frozen-state guard: when interpolation alpha clamps to 1.0 (snapshot
  // age ≥ interval), positions stop changing. Skipping updateFleet on
  // back-to-back frozen frames avoids re-feeding ~6900 features into
  // the GeoJSON source for nothing. Scheduled fleet has no equivalent
  // (trip-progress driven, always advancing).
  let lastFleetAlpha: number | null = null;
  function frame(): void {
    const now = performance.now();
    const alpha = store.getAlpha(now);
    const isFrozen =
      alpha === null || (alpha === 1 && lastFleetAlpha === 1);
    if (!isFrozen) {
      const positions = store.getInterpolated(now);
      updateFleet(map, positions);
    }
    lastFleetAlpha = alpha;
    const nowSec = nowSecondsIstanbul();
    const allScheduled: InterpolatedScheduledTrip[] = [];
    for (const fleet of scheduledFleets.values()) {
      const slice = fleet.getInterpolated(nowSec);
      for (let i = 0; i < slice.length; i++) allScheduled.push(slice[i]);
    }
    updateScheduled(map, allScheduled);
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
}

function startScheduledPolling(): void {
  async function pollOnce(): Promise<void> {
    const results = await Promise.allSettled(
      SCHEDULED_MODES.map(async (mode) => {
        const data = await fetchActiveTrips(mode);
        const fleet = scheduledFleets.get(mode)!;
        const result = await fleet.setActiveTrips(data.trips);
        return { mode, count: data.count, prepared: fleet.size(), shapeCache: fleet.shapeCacheSize(), result };
      }),
    );
    for (const r of results) {
      if (r.status === 'fulfilled') {
        const { mode, count, prepared, shapeCache, result } = r.value;
        console.log(
          `[scheduled] ${mode}: ${count} active, prepared=${prepared}, shapeCache=${shapeCache} ` +
          `(noShape=${result.skippedNoShape} snapFail=${result.skippedSnapFail})`,
        );
      } else {
        console.warn('[scheduled] poll failed', r.reason);
      }
    }
  }
  void pollOnce();
  setInterval(() => void pollOnce(), SCHEDULED_POLL_INTERVAL_MS);
}

function startRealtime(): void {
  let pollTimer: ReturnType<typeof setInterval> | null = null;
  let fallbackTimer: ReturnType<typeof setTimeout> | null = null;

  function pushSnapshot(snap: VehicleSnapshot): void {
    store.push(snap);
    indicator.setTimestamp(Date.parse(snap.timestamp));
    // KM5-e.2: panel "İETT Otobüs (n) / Metrobüs (n)" toggle sayaçları
    // her snapshot'ta yenilenir. Interpolation aralığında sayım değişmez,
    // sadece push'ta — düşük frekans (60sn).
    routePanel?.setVehicleCounts(store.countByMetrobus());
  }

  async function pollOnce(): Promise<void> {
    try {
      const snap = await fetchLiveVehicles();
      console.log(
        `[rest] snapshot: ${snap.vehicle_count} vehicles, ` +
        `${snap.vehicles.length} in payload`,
      );
      pushSnapshot(snap);
    } catch (err) {
      console.warn('[rest] poll failed', err);
    }
  }

  function startPolling(): void {
    if (pollTimer !== null) return;
    console.log('[rest] starting fallback polling (60s)');
    void pollOnce();
    pollTimer = setInterval(() => void pollOnce(), REST_POLL_INTERVAL_MS);
  }

  function stopPolling(): void {
    if (pollTimer === null) return;
    console.log('[rest] stopping fallback polling');
    clearInterval(pollTimer);
    pollTimer = null;
  }

  function armFallback(): void {
    if (fallbackTimer !== null) return;
    fallbackTimer = setTimeout(() => {
      fallbackTimer = null;
      if (!ws.isOpen()) startPolling();
    }, REST_FALLBACK_DELAY_MS);
  }

  const ws = connectWebSocket({
    onSnapshot: pushSnapshot,
    onConnected: () => {
      if (fallbackTimer !== null) {
        clearTimeout(fallbackTimer);
        fallbackTimer = null;
      }
      stopPolling();
    },
    onDisconnected: () => {
      armFallback();
    },
  });

  armFallback();
}

(window as any).__map = map;