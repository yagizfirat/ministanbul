interface VehiclePosition {
  lat: number;
  lon: number;
}

export interface InterpolatedPos {
  lat: number;
  lon: number;
}

// V2-ready signature: vehicleId + optional polyline reserved for KM4 (Faz 4)
// when route polylines drive interpolation along the geometry instead of LERP.
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
