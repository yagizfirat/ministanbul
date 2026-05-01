import type { Map as MapLibreMap, GeoJSONSource } from 'maplibre-gl';
import type { InterpolatedScheduledTrip } from '../simulation/scheduled_trip';

const SOURCE_ID = 'scheduled';
const LAYER_ID = 'scheduled-circles';

const COLOR_METRO = '#60a5fa';
const COLOR_OUTLINE = '#1e3a8a';

interface ScheduledFeature {
  type: 'Feature';
  geometry: { type: 'Point'; coordinates: [number, number] };
  properties: { trip_id: string; mode: string };
}

interface ScheduledCollection {
  type: 'FeatureCollection';
  features: ScheduledFeature[];
}

const EMPTY_FC: ScheduledCollection = { type: 'FeatureCollection', features: [] };

export function initScheduledLayer(map: MapLibreMap): void {
  map.addSource(SOURCE_ID, { type: 'geojson', data: EMPTY_FC });
  map.addLayer({
    id: LAYER_ID,
    type: 'circle',
    source: SOURCE_ID,
    paint: {
      'circle-radius': [
        'interpolate', ['linear'], ['zoom'],
        10, 3,
        14, 5,
        18, 8,
      ],
      'circle-color': COLOR_METRO,
      'circle-stroke-width': 1,
      'circle-stroke-color': COLOR_OUTLINE,
    },
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
    const p = positions[i];
    features[i] = {
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [p.lon, p.lat] },
      properties: { trip_id: p.trip_id, mode: p.mode },
    };
  }
  source.setData({ type: 'FeatureCollection', features });
}
