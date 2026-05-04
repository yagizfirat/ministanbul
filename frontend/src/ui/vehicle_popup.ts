// Faz 6 KM1 alt-iş g — vehicle nokta tıklama popup'ı.
// KM5-d (Spec §3.3, §5.8): otobüs minimal + raylı/vapur zengin (sonraki
// 5 durak listesi). Mapping retire (Ek A.18 R12) sonrası İETT bus için
// hat etiketi gösterilmiyor — sadece "İETT Otobüs · KapiNo X". Metrobüs
// ayrımı yok (categorize sinyali %22 yanlış kararıyla v0.8.0 vizyonunda
// monolitik kütle olarak tutuldu).
//
// Veri kaynakları:
// - props (id, route_id, trip_id, mode): map feature.properties
// - meta (RouteSummary): RouteStore lookup, hat ad/güzergah/agency
// - context (ScheduledPopupContext): scheduled vehicle için PreparedTrip +
//   nowSec; computeNextStops anlık olarak k+1...k+5 durağı çeker.

import { Popup, type Map as MapLibreMap, type LngLat } from 'maplibre-gl';
import type { RouteStore } from '../state/route_store';
import type { RouteSummary } from '../data/api';
import type { PreparedTrip } from '../simulation/scheduled_trip';
import { computeNextStops, formatEta, type NextStop } from '../simulation/next_stops';
import { isMojibake } from '../util/turkish_normalize';

export type VehicleSource = 'iett' | 'scheduled';

export interface VehicleProps {
  // İETT vehicle: id (KapiNo)
  // Scheduled: trip_id, route_id, mode
  id?: string;
  trip_id?: string;
  route_id?: string;
  mode?: string;
  // KM5-e.1 (backend) → KM-c.2 (popup): metrobüs hatları için ayrı label.
  is_metrobus?: boolean;
}

export interface ScheduledPopupContext {
  nowSec: number;
  prepared: PreparedTrip | null;
}

export function showVehiclePopup(
  map: MapLibreMap,
  lngLat: LngLat,
  props: VehicleProps,
  source: VehicleSource,
  routeStore: RouteStore,
  context?: ScheduledPopupContext,
): Popup {
  const meta = props.route_id ? routeStore.getMeta(props.route_id) : null;
  const html = buildPopupHtml(props, source, meta, context);
  return new Popup({ closeOnClick: true, maxWidth: '320px' })
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
  context?: ScheduledPopupContext,
): string {
  return source === 'iett'
    ? renderIettPopup(props)
    : renderScheduledPopup(props, meta, context);
}

function renderTitleRow(meta: RouteSummary): string {
  const longRaw = meta.long_name ?? '';
  // KM-c.1: mojibake durumda bozuk metni hiç render etme — sadece uyarı.
  // Önceki davranış (⚠ + bozuk metin) Yağız 2026-05-04 smoke'da kafa
  // karıştırıcı bulundu (Spec Ek A.19 borç #3).
  const longHtml = isMojibake(longRaw)
    ? `<span class="vehicle-popup__mojibake" style="color:#f59e0b" title="GTFS feed bozuk">⚠ Hat adı okunamıyor</span>`
    : escapeHtml(longRaw);
  return `<div class="vehicle-popup__title">
    <span class="vehicle-popup__short">${escapeHtml(meta.short_name)}</span>
    <span class="vehicle-popup__long">${longHtml}</span>
  </div>`;
}

function renderNextStopsBlock(stops: readonly NextStop[]): string {
  if (stops.length === 0) {
    return `<div class="vehicle-popup__next-stops">
      <div class="vehicle-popup__next-stops-header">Sonraki duraklar</div>
      <div class="vehicle-popup__empty">Sonraki durak yok (terminus)</div>
    </div>`;
  }
  const rows = stops
    .map(
      (s) => `<div class="vehicle-popup__stop">
        <span class="vehicle-popup__stop-name">${escapeHtml(s.stopName)}</span>
        <span class="vehicle-popup__stop-time">${s.scheduled}</span>
        <span class="vehicle-popup__stop-eta">${escapeHtml(formatEta(s.etaSeconds))}</span>
      </div>`,
    )
    .join('');
  return `<div class="vehicle-popup__next-stops">
    <div class="vehicle-popup__next-stops-header">Sonraki duraklar</div>
    ${rows}
  </div>`;
}

function renderScheduledPopup(
  _props: VehicleProps,
  meta: RouteSummary | null,
  context: ScheduledPopupContext | undefined,
): string {
  if (!meta) {
    return `<div class="vehicle-popup">
      <div class="vehicle-popup__unmapped">Hat metadata bulunamadı</div>
      <div class="vehicle-popup__source">Tarife-bazlı simülasyon</div>
    </div>`;
  }
  const prepared = context?.prepared ?? null;
  const nextStopsHtml =
    prepared !== null
      ? renderNextStopsBlock(computeNextStops(prepared, context!.nowSec, 5))
      : '';
  return `<div class="vehicle-popup vehicle-popup--rich">
    ${renderTitleRow(meta)}
    <div class="vehicle-popup__operator">${escapeHtml(meta.agency_name)}</div>
    ${nextStopsHtml}
    <div class="vehicle-popup__source">Tarife-bazlı simülasyon</div>
  </div>`;
}

function renderIettPopup(props: VehicleProps): string {
  // KM5-d: hat etiketi/uyarısı yok. Mapping kapalı, kütle UX (Spec §3.3,
  // Ek A.18 R12). f-polish-3 "henüz hat eşlemesi yapılmamış" mesajı
  // silindi — bilinçli kapatma kararı, pipeline güncellenme değil.
  // KM-c.2: is_metrobus=true ise "Metrobüs" label, değilse "İETT Otobüs".
  const label = props.is_metrobus === true ? 'Metrobüs' : 'İETT Otobüs';
  const kapi = `<b>${escapeHtml(props.id ?? '?')}</b>`;
  return `<div class="vehicle-popup">
    <div class="vehicle-popup__title">
      <span class="vehicle-popup__short">${label}</span>
    </div>
    <div class="vehicle-popup__kapi">KapiNo: ${kapi}</div>
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
