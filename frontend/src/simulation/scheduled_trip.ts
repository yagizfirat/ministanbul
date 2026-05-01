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
}

export interface PreparedTrip {
  trip_id: string;
  route_id: string;
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
  lon: number;
  lat: number;
  bearing: number | null;
  mode: string;
}

export function prepareTrip(trip: ActiveTrip, shape: LonLat[]): PreparedTrip | null {
  if (trip.stop_times.length < 2) return null;
  if (shape.length < 2) return null;

  // direction_id=1 → reverse the shape so the trip walks start → end on the
  // working polyline. Reverse copy (`[...shape].reverse()`) keeps the cached
  // forward shape in route_lines_layer untouched.
  const polyline: LonLat[] =
    trip.direction_id === 1 ? [...shape].reverse() : [...shape];
  const cumDist = cumulativeDistances(polyline);

  const projections: StopProjection[] = [];
  for (const st of trip.stop_times) {
    const snap = snapToPolyline([st.lon, st.lat], polyline, cumDist);
    if (snap === null) return null; // out-of-bounds stop drops the whole trip
    projections.push({
      arrivalSec: st.arrival_seconds,
      arcLengthM: snap.arcLength,
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
    return { trip_id: prep.trip_id, lon: pose.lon, lat: pose.lat,
             bearing: pose.bearing, mode: prep.mode };
  }
  const a = sps[i];
  const b = sps[i + 1];
  const dt = b.arrivalSec - a.arrivalSec;
  const t = dt === 0 ? 0 : Math.min(1, Math.max(0, (nowSec - a.arrivalSec) / dt));
  const arcLen = a.arcLengthM + t * (b.arcLengthM - a.arcLengthM);
  const pose = pointAtArcLength(arcLen, prep.polyline, prep.cumDist);
  return {
    trip_id: prep.trip_id,
    lon: pose.lon,
    lat: pose.lat,
    bearing: pose.bearing,
    mode: prep.mode,
  };
}

// Type alias used by tests/scheduled_fleet.
export type { ActiveTrip, ActiveTripStopTime };
