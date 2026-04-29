import type { Map as MapLibreMap } from 'maplibre-gl';
import { fetchRouteShape, type RouteSummary } from '../data/api';
import { addRouteToMap, removeRouteFromMap } from '../render/route_lines_layer';
import { colorForMode } from './mode_colors';

export type AddOutcome = 'added' | 'skipped' | 'no-shape';
export type RouteListener = (routeId: string) => void;

interface RouteEntry {
  summary: RouteSummary;
  hasShape: boolean;
}

// Single source of truth for which routes are on the map. KM3 only adds the
// always-visible set on load; KM6 panel will call add/remove on toggle.
export class RouteStore {
  private readonly map: MapLibreMap;
  private entries = new Map<string, RouteEntry>();
  private summariesByRouteId = new Map<string, RouteSummary>();
  private addedListeners: RouteListener[] = [];
  private removedListeners: RouteListener[] = [];

  constructor(map: MapLibreMap) {
    this.map = map;
  }

  registerSummaries(summaries: RouteSummary[]): void {
    for (const s of summaries) this.summariesByRouteId.set(s.route_id, s);
  }

  has(routeId: string): boolean {
    return this.entries.has(routeId);
  }

  getAll(): RouteSummary[] {
    return Array.from(this.summariesByRouteId.values());
  }

  async add(routeId: string): Promise<AddOutcome> {
    if (this.entries.has(routeId)) return 'skipped';
    const summary = this.summariesByRouteId.get(routeId);
    if (!summary) {
      throw new Error(`RouteStore.add(${routeId}): unknown route — call registerSummaries first`);
    }
    const shape = await fetchRouteShape(routeId);
    if (shape === null) {
      this.entries.set(routeId, { summary, hasShape: false });
      return 'no-shape';
    }
    addRouteToMap(this.map, routeId, summary.mode, colorForMode(summary.mode), shape);
    this.entries.set(routeId, { summary, hasShape: true });
    for (const fn of this.addedListeners) fn(routeId);
    return 'added';
  }

  remove(routeId: string): void {
    const entry = this.entries.get(routeId);
    if (!entry) return;
    if (entry.hasShape) removeRouteFromMap(this.map, routeId);
    this.entries.delete(routeId);
    for (const fn of this.removedListeners) fn(routeId);
  }

  onRouteAdded(fn: RouteListener): void {
    this.addedListeners.push(fn);
  }

  onRouteRemoved(fn: RouteListener): void {
    this.removedListeners.push(fn);
  }
}
