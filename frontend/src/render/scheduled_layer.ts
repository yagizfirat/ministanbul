import type {
  Map as MapLibreMap,
  GeoJSONSource,
  ExpressionSpecification,
  DataDrivenPropertyValueSpecification,
} from 'maplibre-gl';
import type { InterpolatedScheduledTrip } from '../simulation/scheduled_trip';
import {
  SCHEDULED_VEHICLE_COLORS,
  SCHEDULED_VEHICLE_FALLBACK,
} from '../state/mode_colors';

const SOURCE_ID = 'scheduled';
const LAYER_ID = 'scheduled-circles';

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

function modeMatchExpression(field: 'fill' | 'stroke'): DataDrivenPropertyValueSpecification<string> {
  // Build: ['match', ['get', 'mode'], 'metro', '#xxx', 'marmaray', '#xxx', ..., fallback]
  const branches: (string | string[])[] = [];
  for (const [mode, colors] of Object.entries(SCHEDULED_VEHICLE_COLORS)) {
    branches.push(mode, colors[field]);
  }
  return [
    'match',
    ['get', 'mode'],
    ...branches,
    SCHEDULED_VEHICLE_FALLBACK[field],
  ] as unknown as ExpressionSpecification;
}

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
      'circle-color': modeMatchExpression('fill'),
      'circle-stroke-width': 1,
      'circle-stroke-color': modeMatchExpression('stroke'),
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
