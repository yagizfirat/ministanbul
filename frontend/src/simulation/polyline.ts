export type LonLat = [number, number];
export type Polyline = ReadonlyArray<LonLat>;

export interface InterpolatedPose {
  lat: number;
  lon: number;
  bearing: number | null;
}

export interface SnapResult {
  arcLength: number;
  distFromPoint: number;
  segIdx: number;
  t: number;
}

export interface PointOnPolyline {
  lon: number;
  lat: number;
  bearing: number | null;
}

export const SNAP_THRESHOLD_M = 500;

const EARTH_RADIUS_M = 6_371_008.8;

function toRad(deg: number): number {
  return (deg * Math.PI) / 180;
}

function haversine(a: LonLat, b: LonLat): number {
  const phi1 = toRad(a[1]);
  const phi2 = toRad(b[1]);
  const dPhi = toRad(b[1] - a[1]);
  const dLambda = toRad(b[0] - a[0]);
  const h =
    Math.sin(dPhi / 2) ** 2 +
    Math.cos(phi1) * Math.cos(phi2) * Math.sin(dLambda / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.asin(Math.min(1, Math.sqrt(h)));
}

export function cumulativeDistances(polyline: Polyline): number[] {
  if (polyline.length === 0) return [];
  const cum: number[] = [0];
  for (let i = 1; i < polyline.length; i++) {
    cum.push(cum[i - 1] + haversine(polyline[i - 1], polyline[i]));
  }
  return cum;
}

interface SegmentProjection {
  t: number;
  distM: number;
}

function projectToSegment(p: LonLat, a: LonLat, b: LonLat): SegmentProjection {
  const latRef = toRad((a[1] + b[1]) / 2);
  const cosLat = Math.cos(latRef);
  const abx = toRad(b[0] - a[0]) * cosLat * EARTH_RADIUS_M;
  const aby = toRad(b[1] - a[1]) * EARTH_RADIUS_M;
  const apx = toRad(p[0] - a[0]) * cosLat * EARTH_RADIUS_M;
  const apy = toRad(p[1] - a[1]) * EARTH_RADIUS_M;
  const len2 = abx * abx + aby * aby;
  if (len2 === 0) {
    return { t: 0, distM: haversine(p, a) };
  }
  const tRaw = (apx * abx + apy * aby) / len2;
  const t = Math.max(0, Math.min(1, tRaw));
  const closest: LonLat = [a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])];
  return { t, distM: haversine(p, closest) };
}

export function snapToPolyline(
  point: LonLat,
  polyline: Polyline,
  cumDist: number[],
): SnapResult | null {
  if (polyline.length === 0) return null;
  if (polyline.length === 1) {
    const distM = haversine(point, polyline[0]);
    if (distM > SNAP_THRESHOLD_M) return null;
    return { arcLength: 0, distFromPoint: distM, segIdx: 0, t: 0 };
  }
  let best: SnapResult = {
    arcLength: 0,
    distFromPoint: Infinity,
    segIdx: 0,
    t: 0,
  };
  for (let i = 0; i < polyline.length - 1; i++) {
    const proj = projectToSegment(point, polyline[i], polyline[i + 1]);
    if (proj.distM < best.distFromPoint) {
      const segLen = cumDist[i + 1] - cumDist[i];
      best = {
        arcLength: cumDist[i] + proj.t * segLen,
        distFromPoint: proj.distM,
        segIdx: i,
        t: proj.t,
      };
    }
  }
  if (best.distFromPoint > SNAP_THRESHOLD_M) return null;
  return best;
}

function bearingBetween(a: LonLat, b: LonLat): number {
  const dLon = b[0] - a[0];
  const dLat = b[1] - a[1];
  if (dLon === 0 && dLat === 0) return 0;
  const latRef = toRad((a[1] + b[1]) / 2);
  const theta = Math.atan2(dLon * Math.cos(latRef), dLat);
  return (((theta * 180) / Math.PI) + 360) % 360;
}

export function pointAtArcLength(
  arcLen: number,
  polyline: Polyline,
  cumDist: number[],
): PointOnPolyline {
  if (polyline.length === 1) {
    return { lon: polyline[0][0], lat: polyline[0][1], bearing: null };
  }
  const total = cumDist[cumDist.length - 1];
  const s = Math.max(0, Math.min(total, arcLen));
  let i = 0;
  while (i < polyline.length - 2 && s > cumDist[i + 1]) i++;
  const segLen = cumDist[i + 1] - cumDist[i];
  const t = segLen === 0 ? 0 : (s - cumDist[i]) / segLen;
  const a = polyline[i];
  const b = polyline[i + 1];
  return {
    lon: a[0] + t * (b[0] - a[0]),
    lat: a[1] + t * (b[1] - a[1]),
    bearing: bearingBetween(a, b),
  };
}

export function interpolateAlongPolyline(
  t0: LonLat,
  t1: LonLat,
  polyline: Polyline,
  alpha: number,
): InterpolatedPose | null {
  if (polyline.length === 0) return null;
  const a = Math.max(0, Math.min(1, alpha));
  const cum = cumulativeDistances(polyline);
  const snap0 = snapToPolyline(t0, polyline, cum);
  const snap1 = snapToPolyline(t1, polyline, cum);
  if (snap0 === null || snap1 === null) return null;
  const arcLen = snap0.arcLength + a * (snap1.arcLength - snap0.arcLength);
  const pt = pointAtArcLength(arcLen, polyline, cum);
  return { lat: pt.lat, lon: pt.lon, bearing: pt.bearing };
}
