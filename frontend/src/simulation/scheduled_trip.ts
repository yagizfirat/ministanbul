import type { ActiveTrip, ActiveTripStopTime } from '../data/api';
import {
  cumulativeDistances,
  pointAtArcLength,
  snapToPolyline,
  type LonLat,
} from './polyline';

export interface StopProjection {
  arrivalSec: number;
  arcLengthM: number;
  // KM5-d: popup'ta sonraki durak listesi için (Spec §5.8). prepareTrip
  // backend'den gelen stop_name + sequence'ı projection'a yansıtır;
  // computeNextStops bu projection üzerinden anlık (vehicle interpolated
  // pozisyonundan bağımsız) k+1...k+5 durağı çeker.
  stopName: string;
  sequence: number;
}

export interface PreparedTrip {
  trip_id: string;
  route_id: string;
  short_name: string;
  direction_id: number;
  mode: string;
  polyline: LonLat[];
  cumDist: number[];
  stopProjections: StopProjection[];
  firstArrSec: number;
  lastArrSec: number;
}

export interface InterpolatedScheduledTrip {
  trip_id: string;
  route_id: string;
  short_name: string;
  lon: number;
  lat: number;
  bearing: number | null;
  mode: string;
}

export function prepareTrip(trip: ActiveTrip, shape: LonLat[]): PreparedTrip | null {
  if (trip.stop_times.length < 2) return null;
  if (shape.length < 2) return null;

  // Backend serves each direction's shape in its own forward order; the
  // shape lookup is shape_id-keyed, so no reverse is needed. direction_id
  // is metadata only at this stage.
  const polyline: LonLat[] = shape.slice();
  const cumDist = cumulativeDistances(polyline);

  const projections: StopProjection[] = [];
  for (const st of trip.stop_times) {
    const snap = snapToPolyline([st.lon, st.lat], polyline, cumDist);
    if (snap === null) return null; // out-of-bounds stop drops the whole trip
    projections.push({
      arrivalSec: st.arrival_seconds,
      arcLengthM: snap.arcLength,
      stopName: st.stop_name,
      sequence: st.sequence,
    });
  }

  // Stop_times come pre-sorted by sequence (StopTime.Meta.ordering); sort on
  // arrivalSec so binary search is monotone even if the upstream order ever
  // shifts. For non-monotone arc-length (rare backtracking shapes) we fall
  // back to clamping during render — the projection list still drives time.
  projections.sort((a, b) => a.arrivalSec - b.arrivalSec);

  const firstArrSec = projections[0].arrivalSec;
  const lastArrSec = projections[projections.length - 1].arrivalSec;

  return {
    trip_id: trip.trip_id,
    route_id: trip.route_id,
    short_name: trip.route_short_name,
    direction_id: trip.direction_id,
    mode: trip.mode,
    polyline,
    cumDist,
    stopProjections: projections,
    firstArrSec,
    lastArrSec,
  };
}

export function interpolateScheduledTrip(
  prep: PreparedTrip,
  nowSec: number,
): InterpolatedScheduledTrip | null {
  if (nowSec < prep.firstArrSec || nowSec > prep.lastArrSec) return null;
  const sps = prep.stopProjections;

  // Binary search: largest i such that sps[i].arrivalSec <= nowSec.
  let lo = 0;
  let hi = sps.length - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >>> 1;
    if (sps[mid].arrivalSec <= nowSec) lo = mid;
    else hi = mid - 1;
  }
  const i = lo;
  if (i >= sps.length - 1) {
    // Right at (or past) the last stop — emit the last stop pose.
    const pose = pointAtArcLength(sps[i].arcLengthM, prep.polyline, prep.cumDist);
    return {
      trip_id: prep.trip_id,
      route_id: prep.route_id,
      short_name: prep.short_name,
      lon: pose.lon,
      lat: pose.lat,
      bearing: pose.bearing,
      mode: prep.mode,
    };
  }
  const a = sps[i];
  const b = sps[i + 1];
  const dt = b.arrivalSec - a.arrivalSec;
  const t = dt === 0 ? 0 : Math.min(1, Math.max(0, (nowSec - a.arrivalSec) / dt));
  const arcLen = a.arcLengthM + t * (b.arcLengthM - a.arcLengthM);
  const pose = pointAtArcLength(arcLen, prep.polyline, prep.cumDist);
  return {
    trip_id: prep.trip_id,
    route_id: prep.route_id,
    short_name: prep.short_name,
    lon: pose.lon,
    lat: pose.lat,
    bearing: pose.bearing,
    mode: prep.mode,
  };
}

// Type alias used by tests/scheduled_fleet.
export type { ActiveTrip, ActiveTripStopTime };
