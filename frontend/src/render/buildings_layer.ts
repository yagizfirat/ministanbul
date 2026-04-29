import type { Map as MapLibreMap } from 'maplibre-gl';

const VECTOR_SOURCE_ID = 'openmaptiles';
const LAYER_ID = 'buildings-3d';

export function initBuildingsLayer(map: MapLibreMap, beforeId?: string): void {
  map.addLayer(
    {
      id: LAYER_ID,
      type: 'fill-extrusion',
      source: VECTOR_SOURCE_ID,
      'source-layer': 'building',
      minzoom: 14,
      paint: {
        'fill-extrusion-color': [
          'interpolate', ['linear'], ['get', 'render_height'],
          0, '#cbd5e1',
          50, '#94a3b8',
          200, '#64748b',
        ],
        'fill-extrusion-height': ['get', 'render_height'],
        'fill-extrusion-base': ['get', 'render_min_height'],
        'fill-extrusion-opacity': 0.85,
      },
    },
    beforeId,
  );
}
