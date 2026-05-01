import type { Map as MapLibreMap, GeoJSONSource } from 'maplibre-gl';
import type { InterpolatedVehicle } from '../state/snapshot_store';
import { MODE_FALLBACK_COLORS } from '../styling/route_colors';

const SOURCE_ID = 'fleet';
const LAYER_ID = 'fleet-circles';

// Faz 6 KM1 alt-iş d: tüm İETT araçları İBB belediye sarısı.
// Mapped/unmapped ayrımı renk yerine border ile (mavi/kırmızı kaldırıldı —
// kırmızı "hata" çağrışımı yapıyordu, oysa unmapped doğal bir durum,
// spec §A.13/A.14).
const COLOR_FILL = MODE_FALLBACK_COLORS.bus;
const COLOR_STROKE_MAPPED = '#3a2a00'; // koyu kahve — sarının HSL koyu tonu
const STROKE_WIDTH_MAPPED = 1.5;
const STROKE_WIDTH_UNMAPPED = 0;

interface FleetFeatureProperties {
  id: string;
  // route_id is set ONLY for mapped vehicles. The paint expression
  // uses ['has', 'route_id'] to draw the border.
  route_id?: string;
}

interface FleetFeature {
  type: 'Feature';
  geometry: { type: 'Point'; coordinates: [number, number] };
  properties: FleetFeatureProperties;
}

interface FleetCollection {
  type: 'FeatureCollection';
  features: FleetFeature[];
}

const EMPTY_FC: FleetCollection = { type: 'FeatureCollection', features: [] };

// Pure paint factory — focused null → mevcut paint.
// focused dolu → o hattaki İETT vehicle'ları opacity 1.0,
// diğerleri (mapped + unmapped) 0.2 (alt-iş g focus mode).
export function buildFleetPaint(focused: string | null = null) {
  const base = {
    'circle-radius': [
      'interpolate', ['linear'], ['zoom'],
      10, 3,
      14, 6,
    ],
    'circle-color': COLOR_FILL,
    'circle-stroke-width': [
      'case',
      ['has', 'route_id'], STROKE_WIDTH_MAPPED,
      STROKE_WIDTH_UNMAPPED,
    ],
    'circle-stroke-color': COLOR_STROKE_MAPPED,
  } as const;
  if (focused === null) return base;
  return {
    ...base,
    'circle-opacity': [
      'case',
      ['==', ['get', 'route_id'], focused], 1.0,
      0.2,
    ],
    'circle-stroke-opacity': [
      'case',
      ['==', ['get', 'route_id'], focused], 1.0,
      0.2,
    ],
  } as const;
}

export function initFleetLayer(map: MapLibreMap): void {
  map.addSource(SOURCE_ID, { type: 'geojson', data: EMPTY_FC });
  map.addLayer({
    id: LAYER_ID,
    type: 'circle',
    source: SOURCE_ID,
    paint: buildFleetPaint() as unknown as Record<string, unknown>,
  });
}

export function updateFleet(map: MapLibreMap, positions: InterpolatedVehicle[]): void {
  const source = map.getSource(SOURCE_ID) as GeoJSONSource | undefined;
  if (!source) return;
  const features: FleetFeature[] = new Array(positions.length);
  for (let i = 0; i < positions.length; i++) {
    const p = positions[i];
    const props: FleetFeatureProperties = { id: p.id };
    if (p.route_id !== null) props.route_id = p.route_id;
    features[i] = {
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [p.lon, p.lat] },
      properties: props,
    };
  }
  source.setData({ type: 'FeatureCollection', features });
}
