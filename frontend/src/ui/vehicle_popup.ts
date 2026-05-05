// Click popup for vehicle dots.
//   İETT bus: minimal — "İETT Otobüs · KapiNo X" (no route label since
//   the SHATKODU→route_id mapping is disabled). Metrobüs uses the
//   "Metrobüs" label when is_metrobus=true.
//   Scheduled (rail/ferry): rich — title, agency, next 5 stops with ETA.
//
// Inputs:
//   props (id, route_id, trip_id, mode, is_metrobus): MapLibre feature properties
//   meta (RouteSummary): from RouteStore — name/long_name/agency
//   context.prepared + nowSec: drives computeNextStops for the rich popup

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

// Pure helper — produces the popup HTML; all dynamic strings go
// through escapeHtml.
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
  // Hide the broken text entirely when long_name is mojibake; show only
  // a warning — rendering both was confusing in practice.
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
  // Minimal popup: no route label (mapping disabled). is_metrobus=true
  // surfaces a "Metrobüs" label; everything else reads "İETT Otobüs".
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
