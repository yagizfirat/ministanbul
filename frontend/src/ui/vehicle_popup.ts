// Faz 6 KM1 alt-iş g — vehicle nokta tıklama popup'ı.
//
// f-polish-3 madde 2: popup içeriği human-readable.
// İçerik: short_name + long_name (mojibake ⚠ ile) + agency_name.
// Internal id'ler (route_id, trip_id) gizlendi; KapiNo İETT için
// korundu (kullanıcı için anlamlı taşıt kimliği).
//
// Veri kaynağı: feature.properties (id, route_id, mode) + RouteStore
// metadata lookup (short_name, long_name, agency_name).

import { Popup, type Map as MapLibreMap, type LngLat } from 'maplibre-gl';
import type { RouteStore } from '../state/route_store';
import type { RouteSummary } from '../data/api';
import { isMojibake } from '../util/turkish_normalize';

export type VehicleSource = 'iett' | 'scheduled';

export interface VehicleProps {
  // İETT vehicle: id (KapiNo), route_id (mapped ise)
  // Scheduled: trip_id, route_id, mode
  id?: string;
  trip_id?: string;
  route_id?: string;
  mode?: string;
}

export function showVehiclePopup(
  map: MapLibreMap,
  lngLat: LngLat,
  props: VehicleProps,
  source: VehicleSource,
  routeStore: RouteStore,
): Popup {
  const meta = props.route_id ? routeStore.getMeta(props.route_id) : null;
  const html = buildPopupHtml(props, source, meta);
  return new Popup({ closeOnClick: true, maxWidth: '280px' })
    .setLngLat(lngLat)
    .setHTML(html)
    .addTo(map);
}

// Pure helper — RouteStore inject edilmiş metadata + props ile HTML
// üretir. Tüm escape garantili.
export function buildPopupHtml(
  props: VehicleProps,
  source: VehicleSource,
  meta: RouteSummary | null,
): string {
  return source === 'iett'
    ? renderIettPopup(props, meta)
    : renderScheduledPopup(props, meta);
}

function renderTitleRow(meta: RouteSummary): string {
  const longRaw = meta.long_name ?? '';
  const longText = escapeHtml(longRaw);
  const longHtml = isMojibake(longRaw)
    ? `<span style="color:#f59e0b" title="GTFS feed bozuk">⚠ </span>${longText}`
    : longText;
  return `<div class="vehicle-popup__title">
    <span class="vehicle-popup__short">${escapeHtml(meta.short_name)}</span>
    <span class="vehicle-popup__long">${longHtml}</span>
  </div>`;
}

function renderScheduledPopup(_props: VehicleProps, meta: RouteSummary | null): string {
  if (!meta) {
    return `<div class="vehicle-popup">
      <div class="vehicle-popup__unmapped">Hat metadata bulunamadı</div>
      <div class="vehicle-popup__source">Tarife-bazlı simülasyon</div>
    </div>`;
  }
  return `<div class="vehicle-popup">
    ${renderTitleRow(meta)}
    <div class="vehicle-popup__operator">${escapeHtml(meta.agency_name)}</div>
    <div class="vehicle-popup__source">Tarife-bazlı simülasyon</div>
  </div>`;
}

function renderIettPopup(props: VehicleProps, meta: RouteSummary | null): string {
  const kapi = `KapiNo: <b>${escapeHtml(props.id ?? '?')}</b>`;
  if (!meta) {
    return `<div class="vehicle-popup">
      <div>${kapi}</div>
      <div class="vehicle-popup__unmapped">
        Bu araç henüz hat eşlemesi yapılmamış
        <div class="vehicle-popup__unmapped-detail">(mapping pipeline güncelleniyor)</div>
      </div>
      <div class="vehicle-popup__source">İETT canlı</div>
    </div>`;
  }
  return `<div class="vehicle-popup">
    ${renderTitleRow(meta)}
    <div class="vehicle-popup__operator">${escapeHtml(meta.agency_name)}</div>
    <div>${kapi}</div>
    <div class="vehicle-popup__source">İETT canlı</div>
  </div>`;
}

export function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (c) =>
    ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;',
    })[c]!,
  );
}
