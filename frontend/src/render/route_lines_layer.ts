import type { Map as MapLibreMap, GeoJSONSource } from 'maplibre-gl';
import type { ShapeFeature } from '../data/api';
import type { LonLat } from '../simulation/polyline';

const SOURCE_ID = 'routes';
const LAYER_ID = 'route-lines';
const GLOW_LAYER_ID = 'route-lines-glow';

interface RouteFeature {
  type: 'Feature';
  geometry: ShapeFeature['geometry'];
  properties: {
    route_id: string;
    shape_id: string;
    short_name: string;
    mode: string;
    color: string;
  };
}

interface RouteCollection {
  type: 'FeatureCollection';
  features: RouteFeature[];
}

const collection: RouteCollection = { type: 'FeatureCollection', features: [] };
const shapeIndex = new Map<string, LonLat[]>();

// Pure paint factory — focused null → mevcut paint.
// focused dolu → focused hat parlak (opacity 1.0, %50 daha kalın),
// diğerleri sönük (opacity 0.2). Alt-iş g focus mode "ışın kılıcı"
// efektinin route-lines kısmı.
export function buildRouteLinePaint(focused: string | null = null) {
  if (focused === null) {
    return {
      'line-color': ['get', 'color'],
      'line-opacity': 0.85,
      'line-width': [
        'interpolate', ['linear'], ['zoom'],
        10, 2,
        14, 4,
        18, 6,
      ],
    } as const;
  }
  return {
    'line-color': ['get', 'color'],
    'line-opacity': [
      'case',
      ['==', ['get', 'route_id'], focused], 1.0,
      0.2,
    ],
    'line-width': [
      'case',
      ['==', ['get', 'route_id'], focused],
      ['interpolate', ['linear'], ['zoom'], 10, 3, 14, 6, 18, 9],
      ['interpolate', ['linear'], ['zoom'], 10, 2, 14, 4, 18, 6],
    ],
  } as const;
}

// Pure feature builder — addRouteToMap içindeki MapLibre side-effect'i
// (collection.push + setData) test'te zorlamak yerine, properties'i
// üreten saf fonksiyonu izole eder.
export function buildRouteFeature(
  routeId: string,
  shortName: string,
  mode: string,
  color: string,
  shape: ShapeFeature,
): RouteFeature {
  return {
    type: 'Feature',
    geometry: shape.geometry,
    properties: {
      route_id: routeId,
      shape_id: shape.properties.shape_id,
      short_name: shortName,
      mode,
      color,
    },
  };
}

// Glow halo paint — focused hat altında çift layer ışın kılıcı
// efekti. Filter ile başlangıçta hiçbir feature match etmez (focused
// null), focus aktif olunca filter focused id'ye set'lenir.
export function buildRouteLineGlowPaint() {
  return {
    'line-color': ['get', 'color'],
    'line-opacity': 0.4,
    'line-width': [
      'interpolate', ['linear'], ['zoom'],
      10, 8,
      14, 16,
      18, 24,
    ],
    'line-blur': 4,
  } as const;
}

export function initRouteLinesLayer(map: MapLibreMap, beforeId?: string): void {
  map.addSource(SOURCE_ID, { type: 'geojson', data: collection });
  // Glow ALTTA — normal route-lines ÜSTTE (DOM order, MapLibre layer
  // stack'inde sonradan eklenen üstte). Önce glow eklenir, sonra
  // route-lines beforeId ile aynı slot'a yerleşir.
  map.addLayer(
    {
      id: GLOW_LAYER_ID,
      type: 'line',
      source: SOURCE_ID,
      layout: { 'line-cap': 'round', 'line-join': 'round' },
      paint: buildRouteLineGlowPaint() as unknown as Record<string, unknown>,
      filter: ['==', ['get', 'route_id'], '__none__'], // initial: hidden
    },
    beforeId,
  );
  map.addLayer(
    {
      id: LAYER_ID,
      type: 'line',
      source: SOURCE_ID,
      layout: { 'line-cap': 'round', 'line-join': 'round' },
      paint: buildRouteLinePaint() as unknown as Record<string, unknown>,
    },
    beforeId,
  );
}

// Focus state değişiminde main.ts tarafından çağrılır.
export function setGlowFocus(map: MapLibreMap, focusedRouteId: string | null): void {
  if (!map.getLayer(GLOW_LAYER_ID)) return;
  map.setFilter(
    GLOW_LAYER_ID,
    focusedRouteId
      ? ['==', ['get', 'route_id'], focusedRouteId]
      : ['==', ['get', 'route_id'], '__none__'],
  );
}

export function addRouteToMap(
  map: MapLibreMap,
  routeId: string,
  mode: string,
  shortName: string,
  color: string,
  shape: ShapeFeature,
): void {
  if (collection.features.some((f) => f.properties.route_id === routeId)) return;
  const feature = buildRouteFeature(routeId, shortName, mode, color, shape);
  collection.features.push(feature);
  shapeIndex.set(feature.properties.shape_id, shape.geometry.coordinates as LonLat[]);
  flush(map);
}

export function removeRouteFromMap(map: MapLibreMap, routeId: string): void {
  const idx = collection.features.findIndex((f) => f.properties.route_id === routeId);
  if (idx === -1) return;
  const [removed] = collection.features.splice(idx, 1);
  shapeIndex.delete(removed.properties.shape_id);
  flush(map);
}

export function getShapeFor(shapeId: string): LonLat[] | null {
  return shapeIndex.get(shapeId) ?? null;
}

// Bbox (min lon, min lat, max lon, max lat) — alt-iş g panel çift
// tıkla zoom için (map.fitBounds tüketir). Route polyline ~500-2000
// vertex, single-pass yeterince hızlı.
export function getRouteBBox(routeId: string): [number, number, number, number] | null {
  const feature = collection.features.find((f) => f.properties.route_id === routeId);
  if (!feature) return null;
  const coords = feature.geometry.coordinates;
  if (coords.length === 0) return null;
  let minLon = Infinity;
  let minLat = Infinity;
  let maxLon = -Infinity;
  let maxLat = -Infinity;
  for (const [lon, lat] of coords) {
    if (lon < minLon) minLon = lon;
    if (lon > maxLon) maxLon = lon;
    if (lat < minLat) minLat = lat;
    if (lat > maxLat) maxLat = lat;
  }
  return [minLon, minLat, maxLon, maxLat];
}

function flush(map: MapLibreMap): void {
  const source = map.getSource(SOURCE_ID) as GeoJSONSource | undefined;
  source?.setData(collection);
}
