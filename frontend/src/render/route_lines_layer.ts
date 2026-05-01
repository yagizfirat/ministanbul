import type { Map as MapLibreMap, GeoJSONSource } from 'maplibre-gl';
import type { ShapeFeature } from '../data/api';
import type { LonLat } from '../simulation/polyline';

const SOURCE_ID = 'routes';
const LAYER_ID = 'route-lines';

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

// Pure paint factory — KM1 alt-iş d patterniyle simetri için
// dışarı export edildi. Test edilebilir + alt-iş c/e'de değişimi
// lokalize eder.
export function buildRouteLinePaint() {
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

export function initRouteLinesLayer(map: MapLibreMap, beforeId?: string): void {
  map.addSource(SOURCE_ID, { type: 'geojson', data: collection });
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

function flush(map: MapLibreMap): void {
  const source = map.getSource(SOURCE_ID) as GeoJSONSource | undefined;
  source?.setData(collection);
}
