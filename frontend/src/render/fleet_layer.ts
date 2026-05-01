import type { Map as MapLibreMap, GeoJSONSource } from 'maplibre-gl';
import type { InterpolatedVehicle } from '../state/snapshot_store';

const SOURCE_ID = 'fleet';
const LAYER_ID = 'fleet-circles';

const COLOR_MAPPED = '#2563eb';   // blue
const COLOR_UNMAPPED = '#dc2626'; // red

interface FleetFeature {
  type: 'Feature';
  geometry: { type: 'Point'; coordinates: [number, number] };
  properties: { id: string; color: string };
}

interface FleetCollection {
  type: 'FeatureCollection';
  features: FleetFeature[];
}

const EMPTY_FC: FleetCollection = { type: 'FeatureCollection', features: [] };

// Pure paint factory — extracted so the expression structure is
// unit-testable and so per-iteration tweaks (KM1 alt-iş d) don't have
// to mutate map.addLayer call sites.
export function buildFleetPaint() {
  return {
    'circle-radius': [
      'interpolate', ['linear'], ['zoom'],
      10, 3,
      14, 6,
    ],
    'circle-color': ['get', 'color'],
    'circle-stroke-width': 0.5,
    'circle-stroke-color': 'rgba(0,0,0,0.3)',
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
    features[i] = {
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [p.lon, p.lat] },
      properties: {
        id: p.id,
        color: p.route_id === null ? COLOR_UNMAPPED : COLOR_MAPPED,
      },
    };
  }
  source.setData({ type: 'FeatureCollection', features });
}
