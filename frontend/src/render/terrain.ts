import type { Map as MapLibreMap } from 'maplibre-gl';

const SOURCE_ID = 'mapterhorn-dem';

export function initTerrain(map: MapLibreMap): void {
  if (!map.getSource(SOURCE_ID)) {
    map.addSource(SOURCE_ID, {
      type: 'raster-dem',
      tiles: ['https://tiles.mapterhorn.com/{z}/{x}/{y}.webp'],
      tileSize: 512,
      encoding: 'terrarium',
      attribution: "<a href='https://mapterhorn.com/attribution'>© Mapterhorn</a>",
    });
  }
  map.setTerrain({ source: SOURCE_ID, exaggeration: 1.0 });
  map.setSky({
    'sky-color': '#87ceeb',
    'horizon-color': '#cbd5e1',
    'fog-color': '#cad2d3',
    'sky-horizon-blend': 0.7,
    'horizon-fog-blend': 0.5,
    'fog-ground-blend': 0.2,
    'atmosphere-blend': 0.5,
  });
}
