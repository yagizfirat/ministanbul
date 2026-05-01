import type { Map as MapLibreMap, GeoJSONSource } from 'maplibre-gl';
import type { InterpolatedScheduledTrip } from '../simulation/scheduled_trip';
import { getRouteColor, lighten } from '../styling/route_colors';

const SOURCE_ID = 'scheduled';
const LAYER_ID = 'scheduled-circles';

// KM1 alt-iş c: scheduled vehicle dot'u kendi hattının polyline
// renginin açık tonu (HSL +0.2L). Stroke ise hattın orijinal koyu
// rengi — polyline ile vehicle aynı renk ailesinden, vehicle "halka
// içinde açık ton" olarak okunuyor.
const LIGHTEN_AMOUNT = 0.2;

interface ScheduledFeature {
  type: 'Feature';
  geometry: { type: 'Point'; coordinates: [number, number] };
  properties: {
    trip_id: string;
    route_id: string;
    mode: string;
    color: string;
    strokeColor: string;
  };
}

interface ScheduledCollection {
  type: 'FeatureCollection';
  features: ScheduledFeature[];
}

const EMPTY_FC: ScheduledCollection = { type: 'FeatureCollection', features: [] };

// Pure paint factory — focused null → mevcut paint.
// focused dolu → o hatın trip'leri opacity 1.0, diğerleri 0.2
// (alt-iş g focus mode).
export function buildScheduledLayerPaint(focused: string | null = null) {
  const base = {
    'circle-radius': [
      'interpolate', ['linear'], ['zoom'],
      10, 3,
      14, 5,
      18, 8,
    ],
    'circle-color': ['get', 'color'],
    'circle-stroke-width': 1,
    'circle-stroke-color': ['get', 'strokeColor'],
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

// Pure feature builder — `getRouteColor + lighten` lookup'ı burada
// yapılır, paint expression sadece property'den okur.
export function buildScheduledFeature(p: InterpolatedScheduledTrip): ScheduledFeature {
  const baseColor = getRouteColor(p.short_name, p.mode);
  return {
    type: 'Feature',
    geometry: { type: 'Point', coordinates: [p.lon, p.lat] },
    properties: {
      trip_id: p.trip_id,
      route_id: p.route_id,
      mode: p.mode,
      color: lighten(baseColor, LIGHTEN_AMOUNT),
      strokeColor: baseColor,
    },
  };
}

export function initScheduledLayer(map: MapLibreMap): void {
  map.addSource(SOURCE_ID, { type: 'geojson', data: EMPTY_FC });
  map.addLayer({
    id: LAYER_ID,
    type: 'circle',
    source: SOURCE_ID,
    paint: buildScheduledLayerPaint() as unknown as Record<string, unknown>,
  });
}

export function updateScheduled(
  map: MapLibreMap,
  positions: InterpolatedScheduledTrip[],
): void {
  const source = map.getSource(SOURCE_ID) as GeoJSONSource | undefined;
  if (!source) return;
  const features: ScheduledFeature[] = new Array(positions.length);
  for (let i = 0; i < positions.length; i++) {
    features[i] = buildScheduledFeature(positions[i]);
  }
  source.setData({ type: 'FeatureCollection', features });
}
