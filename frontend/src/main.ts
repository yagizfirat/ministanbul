import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { connectWebSocket, type VehicleSnapshot } from './data/websocket';
import { fetchLiveVehicles } from './data/api';
import { SnapshotStore } from './state/snapshot_store';
import { initFleetLayer, updateFleet } from './render/fleet_layer';
import { initBuildingsLayer } from './render/buildings_layer';
import { initTerrain } from './render/terrain';
import { createLastUpdateIndicator } from './ui/last_update_indicator';

const ISTANBUL_CENTER: [number, number] = [29.00, 41.04];
const STYLE_URL = 'https://tiles.openfreemap.org/styles/bright';
const REST_FALLBACK_DELAY_MS = 5_000;
const REST_POLL_INTERVAL_MS = 60_000;

const store = new SnapshotStore();
const indicator = createLastUpdateIndicator();

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

map.on('load', () => {
  console.log('[map] loaded');
  initTerrain(map);
  initBuildingsLayer(map);
  initFleetLayer(map);
  startRenderLoop();
  startRealtime();
});

function startRenderLoop(): void {
  function frame(): void {
    const positions = store.getInterpolated(performance.now());
    updateFleet(map, positions);
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
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
