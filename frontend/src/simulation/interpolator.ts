interface VehiclePosition {
  lat: number;
  lon: number;
}

export interface InterpolatedPos {
  lat: number;
  lon: number;
}

// vehicleId + optional polyline are placeholders for an upcoming
// version that snaps the path to route geometry instead of LERPing.
export function interpolatePosition(
  _vehicleId: string,
  t0: VehiclePosition,
  t1: VehiclePosition,
  alpha: number,
  _polyline?: ReadonlyArray<[number, number]>,
): InterpolatedPos {
  return {
    lat: lerp(t0.lat, t1.lat, alpha),
    lon: lerp(t0.lon, t1.lon, alpha),
  };
}

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}
