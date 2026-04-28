import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { connectWebSocket } from './data/websocket';

const ISTANBUL_CENTER: [number, number] = [28.98, 41.02];
const STYLE_URL = 'https://tiles.openfreemap.org/styles/bright';

const map = new maplibregl.Map({
  container: 'map',
  style: STYLE_URL,
  center: ISTANBUL_CENTER,
  zoom: 11,
  pitch: 0,
  bearing: 0,
});

map.on('load', () => {
  console.log('[map] loaded');
  connectWebSocket();
});
