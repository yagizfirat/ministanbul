import type { VehicleSnapshot } from './websocket';

const LIVE_VEHICLES_URL = '/api/vehicles/live/';

export async function fetchLiveVehicles(): Promise<VehicleSnapshot> {
  const res = await fetch(LIVE_VEHICLES_URL, { headers: { Accept: 'application/json' } });
  if (!res.ok) {
    throw new Error(`fetchLiveVehicles failed: HTTP ${res.status}`);
  }
  return (await res.json()) as VehicleSnapshot;
}
