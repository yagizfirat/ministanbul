import type { ActiveTrip } from '../data/api';
import {
  prepareTrip,
  interpolateScheduledTrip,
  type InterpolatedScheduledTrip,
  type PreparedTrip,
} from './scheduled_trip';
import type { LonLat } from './polyline';

export type ShapeLookup = (shapeId: string) => LonLat[] | null;

export interface SetActiveTripsResult {
  added: number;
  retained: number;
  removed: number;
  skippedNoShape: number;
  skippedSnapFail: number;
}

export class ScheduledFleet {
  private prepared = new Map<string, PreparedTrip>();

  setActiveTrips(
    trips: ActiveTrip[],
    shapeLookup: ShapeLookup,
  ): SetActiveTripsResult {
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

    for (const trip of trips) {
      if (this.prepared.has(trip.trip_id)) {
        retained++;
        continue;
      }
      const shapeId = trip.shape_id;
      if (shapeId === null) {
        skippedNoShape++;
        continue;
      }
      const shape = shapeLookup(shapeId);
      if (shape === null) {
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

  size(): number {
    return this.prepared.size;
  }

  // KM3-a direction-bug debug. Removed in KM3-b once the diagnosis is closed.
  _debugEntries(): PreparedTrip[] {
    return Array.from(this.prepared.values());
  }
}
