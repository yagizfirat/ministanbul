import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { connectWebSocket, type VehicleSnapshot } from './data/websocket';
import {
  fetchActiveRoutes,
  fetchActiveTrips,
  fetchAllBusRoutes,
  fetchLiveVehicles,
  type RouteSummary,
} from './data/api';
import { SnapshotStore } from './state/snapshot_store';
import { RouteStore } from './state/route_store';
import { buildFleetPaint, initFleetLayer, updateFleet } from './render/fleet_layer';
import { initBuildingsLayer } from './render/buildings_layer';
import {
  buildRouteLinePaint,
  getRouteBBox,
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
import { createLastUpdateIndicator } from './ui/last_update_indicator';
import { createRoutePanel, type RoutePanelHandle } from './ui/route_panel';
import { showVehiclePopup } from './ui/vehicle_popup';

const ISTANBUL_CENTER: [number, number] = [29.00, 41.04];
const STYLE_URL = 'https://tiles.openfreemap.org/styles/bright';
const REST_FALLBACK_DELAY_MS = 5_000;
const REST_POLL_INTERVAL_MS = 60_000;

// Modes drawn as polylines on app load. Marmaray ships inside `subway` and is
// split out by short_name in api.ts. ferry/metrobus/bus are panel opt-ins
// (KM6) — metrobus polyline waits on Faz 5 OSM snapping (Ek A.10).
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

// Alt-iş g: focus state değişiminde 3 layer paint + glow filter
// güncellenir. Map.on('load') sonrasında subscribe edilir.
function applyFocusPaint(focused: string | null): void {
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

  // KM1 alt-iş f-6 — RoutePanel + route filter wiring.
  // Ferry polyline çizilmez (KM3 paterni) ama panel'de listelenir;
  // scheduled vehicle layer'ı route_id filter'ına tabi olduğu için
  // ferry default visible kalır (vapur scheduled noktalar görünür).
  let ferrySummaries: RouteSummary[] = [];
  try {
    ferrySummaries = await fetchActiveRoutes(['ferry']);
    console.log(`[routes] ferry metadata for panel: ${ferrySummaries.length}`);
  } catch (err) {
    console.warn('[routes] ferry fetch failed', err);
  }

  const initialRoutes = [...polylineSummaries, ...ferrySummaries];
  const initialIds = initialRoutes.map((r) => r.route_id);
  // 5 polyline modu (subway+tram+funicular+marmaray) + ferry = default visible.
  // Bus default hidden — lazy fetch sonrası expandTotalCount.
  routeVisibility = new RouteVisibility(initialIds, initialIds);
  routePanel = createRoutePanel({
    visibility: routeVisibility,
    routes: initialRoutes,
    defaultVisibleIds: initialIds, // Reset hedefi (polyline + ferry)
    onRouteDoubleClick: (routeId) => {
      routeFocus.setFocus(routeId);
      const bbox = getRouteBBox(routeId);
      if (bbox) {
        map.fitBounds(bbox as [number, number, number, number], { padding: 80 });
      }
    },
  });

  // Focus paint listener — alt-iş g.
  routeFocus.subscribe(applyFocusPaint);

  // Polyline tıkla → focus o hat. Map global click → boş alan ise reset.
  map.on('click', 'route-lines', (e) => {
    const rid = e.features?.[0]?.properties?.route_id as string | undefined;
    if (rid) routeFocus.setFocus(rid);
  });
  map.on('click', 'fleet-circles', (e) => {
    if (!e.features?.[0]) return;
    showVehiclePopup(map, e.lngLat, e.features[0].properties as never, 'iett');
  });
  map.on('click', 'scheduled-circles', (e) => {
    if (!e.features?.[0]) return;
    showVehiclePopup(map, e.lngLat, e.features[0].properties as never, 'scheduled');
  });
  map.on('click', (e) => {
    // Layer-spesifik handler'lar zaten yakaladı; boş alana tıklamada
    // queryRenderedFeatures targeted layer'larda boş döner → focus reset.
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
    if (map.getLayer('fleet-circles')) {
      map.setFilter('fleet-circles', routeF as never);
    }
  }
  routeVisibility.subscribe(applyFilters);
  applyFilters();

  // Bus lazy fetch (~9275 hat, page_size=10000 tek seferde).
  routePanel.setBusLoading(true);
  fetchAllBusRoutes()
    .then((busRoutes) => {
      console.log(`[bus] loaded ${busRoutes.length} routes`);
      routeVisibility?.expandTotalCount(busRoutes.length);
      routePanel?.setRoutes([...initialRoutes, ...busRoutes]);
    })
    .catch((err) => {
      console.warn('[bus] fetch failed', err);
      routePanel?.setBusError('Otobüs hatları yüklenemedi');
    })
    .finally(() => routePanel?.setBusLoading(false));
}

function startRenderLoop(): void {
  function frame(): void {
    const positions = store.getInterpolated(performance.now());
    updateFleet(map, positions);
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
  }

  async function pollOnce(): Promise<void> {
    try {
      const snap = await fetchLiveVehicles();
      console.log(
        `[rest] snapshot: ${snap.vehicle_count} vehicles, ` +
        `${snap.mapped_count} mapped, ${snap.vehicles.length} in payload`,
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