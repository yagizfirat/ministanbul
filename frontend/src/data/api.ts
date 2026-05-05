import type { VehicleSnapshot } from './websocket';

const LIVE_VEHICLES_URL = '/api/vehicles/live/';

export async function fetchLiveVehicles(): Promise<VehicleSnapshot> {
  const res = await fetch(LIVE_VEHICLES_URL, { headers: { Accept: 'application/json' } });
  if (!res.ok) {
    throw new Error(`fetchLiveVehicles failed: HTTP ${res.status}`);
  }
  return (await res.json()) as VehicleSnapshot;
}

export interface RouteSummary {
  id: number;
  route_id: string;          // "public:1298" or "iett:NNNN"
  short_name: string;
  long_name: string;
  route_type: number;
  route_type_label: string;
  agency_name: string;
  // App-level mode. Backend returns route_type ints; we map them back via the
  // query mode and post-process subway → marmaray when short_name says so.
  mode: string;
  // Backend categorization flag (settings.METROBUS_SHORT_NAMES);
  // drives the metrobüs render branch on the frontend. Optional for
  // defensive parsing of older responses.
  is_metrobus?: boolean;
}

export interface ShapeFeature {
  type: 'Feature';
  geometry: { type: 'LineString'; coordinates: [number, number][] };
  properties: { shape_id: string };
}

export interface ActiveTripStopTime {
  stop_id: string;
  stop_name: string;
  sequence: number;
  arrival_seconds: number;
  lat: number;
  lon: number;
}

export interface ActiveTrip {
  trip_id: string;
  route_id: string;
  route_short_name: string;
  route_long_name: string;
  shape_id: string | null;
  direction_id: number;
  headsign: string;
  mode: string;
  stop_times: ActiveTripStopTime[];
}

export interface ActiveTripsResponse {
  mode: string;
  now: string;
  count: number;
  trips: ActiveTrip[];
}

export async function fetchActiveTrips(
  mode: string,
  time?: string,
): Promise<ActiveTripsResponse> {
  const qs = new URLSearchParams({ mode });
  if (time) qs.set('time', time);
  const url = `/api/trips/active/?${qs.toString()}`;
  const res = await fetch(url, { headers: { Accept: 'application/json' } });
  if (!res.ok) {
    throw new Error(`fetchActiveTrips(${mode}) failed: HTTP ${res.status}`);
  }
  return (await res.json()) as ActiveTripsResponse;
}

interface BackendRoute {
  id: number;
  route_id: string;
  agency: { name?: string } | null;
  short_name: string;
  long_name: string;
  route_type: number;
  route_type_label: string;
  is_metrobus?: boolean;
}

interface RouteListResponse {
  count: number;
  next: string | null;
  previous: string | null;
  results: BackendRoute[];
}

export async function fetchActiveRoutes(modes: string[]): Promise<RouteSummary[]> {
  const perMode = await Promise.all(modes.map(fetchRoutesForMode));
  return perMode.flat();
}

// Bus için tek seferde fetch (9275 hat). Backend search filter yok →
// frontend in-memory fuzzy match. page_size=10000 override edilebilir
// (KM3-c discovery'de 5000 testte çalışmıştı, 10000 güvenli üst sınır).
export async function fetchAllBusRoutes(): Promise<RouteSummary[]> {
  const url = '/api/routes/?mode=bus&page_size=10000';
  const res = await fetch(url, { headers: { Accept: 'application/json' } });
  if (!res.ok) {
    throw new Error(`fetchAllBusRoutes failed: HTTP ${res.status}`);
  }
  const data = (await res.json()) as RouteListResponse;
  return data.results.map((r) => ({
    id: r.id,
    route_id: r.route_id,
    short_name: r.short_name,
    long_name: r.long_name,
    route_type: r.route_type,
    route_type_label: r.route_type_label,
    agency_name: r.agency?.name ?? '',
    mode: 'bus',
    is_metrobus: r.is_metrobus,
  }));
}

async function fetchRoutesForMode(mode: string): Promise<RouteSummary[]> {
  const url = `/api/routes/?mode=${encodeURIComponent(mode)}&has_shape=true&page_size=200`;
  const res = await fetch(url, { headers: { Accept: 'application/json' } });
  if (!res.ok) {
    throw new Error(`fetchActiveRoutes(${mode}) failed: HTTP ${res.status}`);
  }
  const data = (await res.json()) as RouteListResponse;
  return data.results.map((r) => ({
    id: r.id,
    route_id: r.route_id,
    short_name: r.short_name,
    long_name: r.long_name,
    route_type: r.route_type,
    route_type_label: r.route_type_label,
    agency_name: r.agency?.name ?? '',
    mode: appModeFor(mode, r.short_name),
    is_metrobus: r.is_metrobus,
  }));
}

function appModeFor(queryMode: string, shortName: string): string {
  // İBB feed puts Marmaray under subway (route_type=1). Split it out by
  // short_name so the panel + colors can treat it as its own mode.
  if (queryMode === 'subway') {
    return shortName.startsWith('Marmaray') ? 'marmaray' : 'metro';
  }
  return queryMode;
}

// Returns null when backend says "no shape on this route" (HTTP 204 — expected
// for İETT bus routes; spec Ek A.10).
export async function fetchRouteShape(routeId: string): Promise<ShapeFeature | null> {
  const url = `/api/routes/${routeId}/shape/`;
  const res = await fetch(url, { headers: { Accept: 'application/json' } });
  if (res.status === 204) return null;
  if (!res.ok) {
    throw new Error(`fetchRouteShape(${routeId}) failed: HTTP ${res.status}`);
  }
  return (await res.json()) as ShapeFeature;
}

// Per-shape lookup for scheduled trips. Each direction's shape is a
// separate GTFS row, so trips reference shape_id directly.
export async function fetchShape(shapeId: string): Promise<ShapeFeature> {
  const url = `/api/shapes/${shapeId}/`;
  const res = await fetch(url, { headers: { Accept: 'application/json' } });
  if (!res.ok) {
    throw new Error(`fetchShape(${shapeId}) failed: HTTP ${res.status}`);
  }
  return (await res.json()) as ShapeFeature;
}
