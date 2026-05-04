import { fetchShape, type ActiveTrip } from '../data/api';
import {
  prepareTrip,
  interpolateScheduledTrip,
  type InterpolatedScheduledTrip,
  type PreparedTrip,
} from './scheduled_trip';
import type { LonLat } from './polyline';

export interface SetActiveTripsResult {
  added: number;
  retained: number;
  removed: number;
  skippedNoShape: number;
  skippedSnapFail: number;
}

export class ScheduledFleet {
  private prepared = new Map<string, PreparedTrip>();
  private shapeCache = new Map<string, LonLat[]>();

  async setActiveTrips(trips: ActiveTrip[]): Promise<SetActiveTripsResult> {
    const incomingIds = new Set(trips.map((t) => t.trip_id));
    let added = 0;
    let retained = 0;
    let removed = 0;
    let skippedNoShape = 0;
    let skippedSnapFail = 0;

    for (const id of Array.from(this.prepared.keys())) {
      if (!incomingIds.has(id)) {
        this.prepared.delete(id);
        removed++;
      }
    }

    const newTrips = trips.filter((t) => !this.prepared.has(t.trip_id));
    const heldTrips = trips.length - newTrips.length;
    retained = heldTrips;

    // Collect distinct shape_ids that are not yet cached, then fetch them in
    // parallel. A trip with shape_id=null falls into the noShape bucket.
    const shapeIdsToFetch = new Set<string>();
    for (const t of newTrips) {
      if (t.shape_id !== null && !this.shapeCache.has(t.shape_id)) {
        shapeIdsToFetch.add(t.shape_id);
      }
    }

    if (shapeIdsToFetch.size > 0) {
      const fetches = Array.from(shapeIdsToFetch).map(async (sid) => {
        try {
          const sf = await fetchShape(sid);
          this.shapeCache.set(sid, sf.geometry.coordinates as LonLat[]);
        } catch (err) {
          console.warn(`[scheduled] shape fetch failed for ${sid}`, err);
        }
      });
      await Promise.all(fetches);
    }

    for (const trip of newTrips) {
      const sid = trip.shape_id;
      if (sid === null) {
        skippedNoShape++;
        continue;
      }
      const shape = this.shapeCache.get(sid);
      if (shape === undefined) {
        skippedNoShape++;
        continue;
      }
      const prep = prepareTrip(trip, shape);
      if (prep === null) {
        skippedSnapFail++;
        continue;
      }
      this.prepared.set(trip.trip_id, prep);
      added++;
    }

    return { added, retained, removed, skippedNoShape, skippedSnapFail };
  }

  getInterpolated(nowSec: number): InterpolatedScheduledTrip[] {
    const out: InterpolatedScheduledTrip[] = [];
    for (const prep of this.prepared.values()) {
      const pose = interpolateScheduledTrip(prep, nowSec);
      if (pose !== null) out.push(pose);
    }
    return out;
  }

  // KM5-d: popup zengin versiyonu için PreparedTrip lookup. Click handler
  // trip_id'yi feature.properties'tan okuyup buradan PreparedTrip'i alır
  // ve computeNextStops'a geçirir.
  getPreparedTrip(tripId: string): PreparedTrip | null {
    return this.prepared.get(tripId) ?? null;
  }

  // KM-d.1 fix (Spec Ek A.19 borç #6): ferry/scheduled hatlar için bbox
  // fallback. SnapshotStore İETT canlı kapsamında, polyline modlar
  // route_lines_layer collection'ında — vapur ne ikisinde. Active
  // PreparedTrip'lerin polyline koordinatlarından union bbox hesaplar.
  getRouteBBox(routeId: string): [number, number, number, number] | null {
    return this.getRoutesBBox([routeId]);
  }

  getRoutesBBox(
    routeIds: readonly string[],
  ): [number, number, number, number] | null {
    if (routeIds.length === 0) return null;
    const idSet = new Set(routeIds);
    let minLon = Infinity;
    let minLat = Infinity;
    let maxLon = -Infinity;
    let maxLat = -Infinity;
    let found = false;
    for (const prep of this.prepared.values()) {
      if (!idSet.has(prep.route_id)) continue;
      for (const [lon, lat] of prep.polyline) {
        if (lon < minLon) minLon = lon;
        if (lon > maxLon) maxLon = lon;
        if (lat < minLat) minLat = lat;
        if (lat > maxLat) maxLat = lat;
      }
      found = true;
    }
    return found ? [minLon, minLat, maxLon, maxLat] : null;
  }

  size(): number {
    return this.prepared.size;
  }

  shapeCacheSize(): number {
    return this.shapeCache.size;
  }
}
