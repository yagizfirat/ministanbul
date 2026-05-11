import type { Map as MapLibreMap, GeoJSONSource } from 'maplibre-gl';
import type { InterpolatedVehicle } from '../state/snapshot_store';
import { MODE_FALLBACK_COLORS } from '../styling/route_colors';

const SOURCE_ID = 'fleet';
const LAYER_ID = 'fleet-circles';

// İETT vehicles render as municipal yellow circles; mapped vs unmapped
// is signalled by a dark-brown border (not by color, to avoid the
// "error" connotation of red). Metrobüs vehicles render anthracite
// grey + white border + slightly larger radius to stand out among the
// ~6700 yellow circles.
const COLOR_FILL = MODE_FALLBACK_COLORS.bus;
const COLOR_FILL_METROBUS = '#3A3D40';
const COLOR_STROKE_MAPPED = '#3a2a00';
const COLOR_STROKE_METROBUS = '#FFFFFF';
const STROKE_WIDTH_MAPPED = 1.5;
const STROKE_WIDTH_METROBUS = 1.5;
const STROKE_WIDTH_UNMAPPED = 1;

interface FleetFeatureProperties {
  id: string;
  // Set ONLY for mapped vehicles; absence drives the no-border branch.
  route_id?: string;
  // Categorization flag from backend; drives both color/border case
  // and the bus/metrobüs visibility filter.
  is_metrobus?: boolean;
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

// Pure paint factory. focused=null/[] → base paint; focused=ids → those
// vehicles render at opacity 1.0, the rest at 0.2.
//
// MapLibre style-spec constraint: ['zoom'] expression is only valid as
// the top-level interpolate input — never nested inside a case. So
// per-zoom stops use `interpolate(['zoom'], ...)` at the top with
// `case` only inside each stop's output value.
export function buildFleetPaint(focused: readonly string[] | null = null) {
  const isMetrobusCase = ['==', ['get', 'is_metrobus'], true] as const;
  const base = {
    // LOD: hidden below zoom 7 (city skylines render thousands of
    // sub-pixel circles otherwise); metrobüs +1 over default at every
    // visible stop.
    'circle-radius': [
      'interpolate', ['linear'], ['zoom'],
      7, 0,
      9, ['case', isMetrobusCase, 2, 1],
      10, ['case', isMetrobusCase, 4, 3],
      14, ['case', isMetrobusCase, 7, 6],
    ],
    'circle-color': [
      'case',
      isMetrobusCase, COLOR_FILL_METROBUS,
      COLOR_FILL,
    ],
    // 3-branch case: metrobüs (route_id often null) is checked first,
    // then mapped bus (route_id present), else no border.
    'circle-stroke-width': [
      'case',
      isMetrobusCase, STROKE_WIDTH_METROBUS,
      ['has', 'route_id'], STROKE_WIDTH_MAPPED,
      STROKE_WIDTH_UNMAPPED,
    ],
    'circle-stroke-color': [
      'case',
      isMetrobusCase, COLOR_STROKE_METROBUS,
      COLOR_STROKE_MAPPED,
    ],
  } as const;
  if (focused === null || focused.length === 0) return base;
  return {
    ...base,
    'circle-opacity': [
      'case',
      ['in', ['get', 'route_id'], ['literal', focused]], 1.0,
      0.2,
    ],
    'circle-stroke-opacity': [
      'case',
      ['in', ['get', 'route_id'], ['literal', focused]], 1.0,
      0.2,
    ],
  } as const;
}

// MapLibre filter expression for the bus/metrobüs panel toggles.
// is_metrobus=true vehicles obey metrobusVisible; the rest obey busVisible.
export function buildFleetFilter(
  busVisible: boolean,
  metrobusVisible: boolean,
): unknown {
  return [
    'case',
    ['==', ['get', 'is_metrobus'], true], metrobusVisible,
    busVisible,
  ];
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
    if (p.is_metrobus) props.is_metrobus = true;
    features[i] = {
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [p.lon, p.lat] },
      properties: props,
    };
  }
  source.setData({ type: 'FeatureCollection', features });
}
