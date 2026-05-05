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

// Pure paint factory — focused null/[] → mevcut paint.
// focused string[] → bu hatlar belirgin parlar (opacity 1.0, kalın
// stops 4/7/10), diğerleri belirgin söner (opacity 0.15, ince stops
// 1/2/3 — focused'un yarısının altı, kontrast ≥3x her zoom'da).
//
// v0.8.1 KM-h.2 (Borç #16): non-focused width yarıya indirildi (2/4/6
// → 1/2/3), focused width 1 birim artırıldı (3/6/9 → 4/7/10), non-
// focused opacity 0.2 → 0.15. Glow layer (route-lines-glow) zaten
// focus'a göre filter ile toggle ediliyor — bu fix line katmanının
// kendi kontrastını da büyütür, glow halo'nun üstüne biner.
//
// v0.8.1 KM-a fix (Spec Ek A.19): MapLibre style spec'te ``["zoom"]``
// expression yalnız top-level ``interpolate``/``step`` input'unda
// kullanılabilir; ``case`` içinde nested zoom kabul edilmez ve
// ``setPaintProperty('line-width', …)`` runtime'da hata fırlatır.
// focused dolu paint'i bu nedenle "outer interpolate(zoom) → inner
// data-driven case stops" desenine çevrildi: zoom interpolation top-
// level kalır, her stop'un output'u kendi içinde focused/non-focused
// arası ayrım yapar.
export function buildRouteLinePaint(focused: readonly string[] | null = null) {
  if (focused === null || focused.length === 0) {
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
  const focusedCase = ['in', ['get', 'route_id'], ['literal', focused]] as const;
  return {
    'line-color': ['get', 'color'],
    'line-opacity': [
      'case',
      focusedCase, 1.0,
      0.15,
    ],
    'line-width': [
      'interpolate', ['linear'], ['zoom'],
      10, ['case', focusedCase, 4, 1],
      14, ['case', focusedCase, 7, 2],
      18, ['case', focusedCase, 10, 3],
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
// f-polish-5: array filter, multi-route focus'ta hepsi parlar.
export function setGlowFocus(map: MapLibreMap, focused: readonly string[] | null): void {
  if (!map.getLayer(GLOW_LAYER_ID)) return;
  map.setFilter(
    GLOW_LAYER_ID,
    focused && focused.length > 0
      ? ['in', ['get', 'route_id'], ['literal', focused]]
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

// Bbox (min lon, min lat, max lon, max lat) — panel çift tıkla zoom
// için. Single-route convenience wrapper, multi-route varyant grubu
// için getRoutesBBox kullanılır.
export function getRouteBBox(routeId: string): [number, number, number, number] | null {
  return getRoutesBBox([routeId]);
}

// f-polish-5: union bbox over multiple route_ids (variant group).
// Tüm matching feature'ların coordinates birleşiminin min/max'i.
export function getRoutesBBox(
  routeIds: readonly string[],
): [number, number, number, number] | null {
  if (routeIds.length === 0) return null;
  const idSet = new Set(routeIds);
  let minLon = Infinity;
  let minLat = Infinity;
  let maxLon = -Infinity;
  let maxLat = -Infinity;
  let found = false;
  for (const f of collection.features) {
    if (!idSet.has(f.properties.route_id)) continue;
    for (const [lon, lat] of f.geometry.coordinates) {
      if (lon < minLon) minLon = lon;
      if (lon > maxLon) maxLon = lon;
      if (lat < minLat) minLat = lat;
      if (lat > maxLat) maxLat = lat;
    }
    found = true;
  }
  return found ? [minLon, minLat, maxLon, maxLat] : null;
}

function flush(map: MapLibreMap): void {
  const source = map.getSource(SOURCE_ID) as GeoJSONSource | undefined;
  source?.setData(collection);
}
