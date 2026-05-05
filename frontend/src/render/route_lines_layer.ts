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

// Pure paint factory. focused=null/[] → base paint; focused=ids →
// matching lines render at full opacity and 4/7/10 px (zoom 10/14/18),
// others at 0.15 opacity and 1/2/3 px — kontrast ≥3× at every zoom.
//
// MapLibre style-spec constraint: ['zoom'] expression is only valid as
// the top-level interpolate input — never nested inside a case. So
// per-zoom widths use `interpolate(['zoom'], ...)` at the top with
// `case` only inside each stop's output value.
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

// Glow halo painted under the focused line(s); hidden initially via a
// no-match filter, switched on by setGlowFocus.
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
  // Glow goes underneath; route-lines added second to render on top.
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

// Lights up the glow layer for a single route or a variant-group union.
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

// Bbox [minLon, minLat, maxLon, maxLat] used by panel double-click zoom.
// Single-route convenience wrapper around getRoutesBBox.
export function getRouteBBox(routeId: string): [number, number, number, number] | null {
  return getRoutesBBox([routeId]);
}

// Union bbox over multiple route_ids (e.g. all variants of a group).
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
