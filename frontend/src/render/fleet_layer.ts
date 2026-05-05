import type { Map as MapLibreMap, GeoJSONSource } from 'maplibre-gl';
import type { InterpolatedVehicle } from '../state/snapshot_store';
import { MODE_FALLBACK_COLORS } from '../styling/route_colors';

const SOURCE_ID = 'fleet';
const LAYER_ID = 'fleet-circles';

// Faz 6 KM1 alt-iş d: tüm İETT araçları İBB belediye sarısı.
// Mapped/unmapped ayrımı renk yerine border ile (mavi/kırmızı kaldırıldı —
// kırmızı "hata" çağrışımı yapıyordu, oysa unmapped doğal bir durum,
// spec §A.13/A.14).
//
// KM5-e.2 (Spec §3.3): is_metrobus=true → antrasit gri (kurumsal metrobüs
// hattı görsel kimliği). Backend mapping cache lookup'ı %22 yanlış
// kategori riskiyle gelir (Rapor 12); Yağız bilinçli tolerans (rengin
// yokluğu = %0 bilgi, varlığı = %78 doğru, B yolundan dönüş kararı).
const COLOR_FILL = MODE_FALLBACK_COLORS.bus;
const COLOR_FILL_METROBUS = '#3A3D40';   // antrasit
const COLOR_STROKE_MAPPED = '#3a2a00'; // koyu kahve — sarının HSL koyu tonu
// v0.8.2 KM-c (Spec Ek A.19 #9): metrobüs noktası 6700+ sarı kalabalıkta
// gözle ayırt edilemiyor. Beyaz border antrasit zemin üzerinde maksimum
// kontrast verir; radius +1 birim her zoom seviyesinde göze daha çabuk
// çarpar. Kategori sinyali (KM5-e.1 categorize-only) zaten doğru çalışıyor;
// görsel sunum güçlendirildi.
const COLOR_STROKE_METROBUS = '#FFFFFF';
const STROKE_WIDTH_MAPPED = 1.5;
const STROKE_WIDTH_METROBUS = 1.5;
const STROKE_WIDTH_UNMAPPED = 0;

interface FleetFeatureProperties {
  id: string;
  // route_id is set ONLY for mapped vehicles. The paint expression
  // uses ['has', 'route_id'] to draw the border.
  route_id?: string;
  // KM5-e.2: kategori bayrağı; paint case expression'ında antrasit/sarı
  // ayrımı + filter expression'ında bağımsız toggle için kullanılır.
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

// Pure paint factory — focused null/[] → mevcut paint.
// focused string[] → o hatlardaki İETT vehicle'ları opacity 1.0,
// diğerleri (mapped + unmapped) 0.2. f-polish-5: array filter.
export function buildFleetPaint(focused: readonly string[] | null = null) {
  // v0.8.2 KM-c: metrobüs için her zoom stop'unda +1 birim radius.
  // KM-h.2 / KM-a desenine uygun: outer interpolate(['zoom']) top-level,
  // inner case is_metrobus stops (MapLibre style spec — case içinde
  // nested ['zoom'] yasak, setPaintProperty Error fırlatır).
  const isMetrobusCase = ['==', ['get', 'is_metrobus'], true] as const;
  const base = {
    // v0.8.3 KM-b: LOD low-zoom culling. zoom 7 (ülke ölçeği) altında
    // 6900 nokta görsel olarak okunamaz; radius 0 ile MapLibre rendering
    // pipeline'ı circle'ı erken atlar (fragment shader fully transparent
    // pixel için zaman harcamaz). zoom 9'da küçük (1-2px), zoom 10'dan
    // itibaren mevcut KM-c boyutları (3/4 → 6/7).
    // KM-a guard: case içinde nested ['zoom'] yok (interpolate stops
    // top-level, case yalnız output expression).
    'circle-radius': [
      'interpolate', ['linear'], ['zoom'],
      7, 0,
      9, ['case', isMetrobusCase, 2, 1],
      10, ['case', isMetrobusCase, 4, 3],
      14, ['case', isMetrobusCase, 7, 6],
    ],
    // KM5-e.2: data-driven case — is_metrobus=true → antrasit, else sarı.
    // Field eksik (eski snapshot, defansif) ['get', 'is_metrobus'] undefined
    // dönerse case false'a düşer → sarı default.
    'circle-color': [
      'case',
      isMetrobusCase, COLOR_FILL_METROBUS,
      COLOR_FILL,
    ],
    // v0.8.2 KM-c: 3-branch case. Metrobüs route_id genelde null
    // (mapping retire) — eski `has route_id` branch'i kapsamazdı, şimdi
    // metrobüs öncelikli kontrol. Mapped bus eski davranışla 1.5px
    // koyu kahve border korunur; unmapped bus border'sız kalır.
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

// KM5-e.2: filtre paneli toggle'larına bağlı MapLibre filter expression.
// İki bağımsız boolean: is_metrobus=true vehicle'lar metrobusVisible'a,
// is_metrobus=false (veya yok) vehicle'lar busVisible'a bakar. İkisi de
// false → tüm İETT bus gizli; ikisi true → hepsi görünür (default).
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
