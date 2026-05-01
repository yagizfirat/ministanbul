// Faz 6 KM1 alt-iş g — vehicle nokta tıklama popup'ı.
//
// İki kaynak: 'iett' (canlı sarı noktalar, fleet-circles) ve
// 'scheduled' (tarife-bazlı renkli noktalar, scheduled-circles).
// Popup içeriği farklı: İETT KapiNo + (mapped ise) hat; scheduled
// trip + hat + mod.
//
// Popup HTML'i `escapeHtml` ile sanitize edilir — feed'den gelen
// route_id/short_name string'leri (örn. mojibake'li bus adı) güvenle
// render edilir, XSS riski yok.

import { Popup, type Map as MapLibreMap, type LngLat } from 'maplibre-gl';
import { isMojibake } from '../util/turkish_normalize';

export type VehicleSource = 'iett' | 'scheduled';

export interface VehicleProps {
  // İETT vehicle: id (KapiNo), route_id (mapped ise)
  // Scheduled: trip_id, route_id, short_name, mode
  id?: string;
  trip_id?: string;
  route_id?: string;
  short_name?: string;
  mode?: string;
}

export function showVehiclePopup(
  map: MapLibreMap,
  lngLat: LngLat,
  props: VehicleProps,
  source: VehicleSource,
): Popup {
  const html = buildPopupHtml(props, source);
  const popup = new Popup({ closeOnClick: true, maxWidth: '260px' })
    .setLngLat(lngLat)
    .setHTML(html)
    .addTo(map);
  return popup;
}

// Pure helper — tüm HTML üretimi tek yerde, escape garantili,
// test edilebilir.
export function buildPopupHtml(props: VehicleProps, source: VehicleSource): string {
  return source === 'iett' ? renderIettPopup(props) : renderScheduledPopup(props);
}

function renderIettPopup(props: VehicleProps): string {
  const id = escapeHtml(props.id ?? '?');
  const sn = props.short_name ?? props.route_id ?? '';
  const route = props.route_id
    ? `<div>Hat: <b>${maybeWarn(sn)}${escapeHtml(sn)}</b></div>`
    : `<div style="color:#9ca3af">Hat bilinmiyor (mapping eksik)</div>`;
  return `<div class="vehicle-popup">
    <div>KapiNo: <b>${id}</b></div>
    ${route}
    <div class="vehicle-popup__source">İETT canlı</div>
  </div>`;
}

function renderScheduledPopup(props: VehicleProps): string {
  const trip = escapeHtml(props.trip_id ?? '?');
  const sn = props.short_name ?? props.route_id ?? '?';
  const mode = escapeHtml(props.mode ?? '?');
  return `<div class="vehicle-popup">
    <div>Trip: <b>${escapeHtml(trip)}</b></div>
    <div>Hat: <b>${maybeWarn(sn)}${escapeHtml(sn)}</b></div>
    <div>Mod: ${mode}</div>
    <div class="vehicle-popup__source">Tarife-bazlı simülasyon</div>
  </div>`;
}

function maybeWarn(s: string): string {
  return isMojibake(s) ? '<span style="color:#f59e0b" title="GTFS feed bozuk">⚠ </span>' : '';
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
