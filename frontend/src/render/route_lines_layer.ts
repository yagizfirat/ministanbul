import type { Map as MapLibreMap, GeoJSONSource } from 'maplibre-gl';
import type { ShapeFeature } from '../data/api';

const SOURCE_ID = 'routes';
const LAYER_ID = 'route-lines';

interface RouteFeature {
  type: 'Feature';
  geometry: ShapeFeature['geometry'];
  properties: { route_id: string; mode: string; color: string };
}

interface RouteCollection {
  type: 'FeatureCollection';
  features: RouteFeature[];
}

const collection: RouteCollection = { type: 'FeatureCollection', features: [] };

export function initRouteLinesLayer(map: MapLibreMap, beforeId?: string): void {
  map.addSource(SOURCE_ID, { type: 'geojson', data: collection });
  map.addLayer(
    {
      id: LAYER_ID,
      type: 'line',
      source: SOURCE_ID,
      layout: { 'line-cap': 'round', 'line-join': 'round' },
      paint: {
        'line-color': ['get', 'color'],
        'line-opacity': 0.85,
        'line-width': [
          'interpolate', ['linear'], ['zoom'],
          10, 2,
          14, 4,
          18, 6,
        ],
      },
    },
    beforeId,
  );
}

export function addRouteToMap(
  map: MapLibreMap,
  routeId: string,
  mode: string,
  color: string,
  shape: ShapeFeature,
): void {
  if (collection.features.some((f) => f.properties.route_id === routeId)) return;
  collection.features.push({
    type: 'Feature',
    geometry: shape.geometry,
    properties: { route_id: routeId, mode, color },
  });
  flush(map);
}

export function removeRouteFromMap(map: MapLibreMap, routeId: string): void {
  const idx = collection.features.findIndex((f) => f.properties.route_id === routeId);
  if (idx === -1) return;
  collection.features.splice(idx, 1);
  flush(map);
}

function flush(map: MapLibreMap): void {
  const source = map.getSource(SOURCE_ID) as GeoJSONSource | undefined;
  source?.setData(collection);
}
