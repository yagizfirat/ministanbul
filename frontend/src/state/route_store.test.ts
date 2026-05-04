import { describe, expect, it } from 'vitest';
import type { Map as MapLibreMap } from 'maplibre-gl';
import { RouteStore } from './route_store';
import type { RouteSummary } from '../data/api';

function summary(over: Partial<RouteSummary> = {}): RouteSummary {
  return {
    id: 1,
    route_id: 'public:m2',
    short_name: 'M2',
    long_name: 'YENİKAPI - HACIOSMAN',
    route_type: 1,
    route_type_label: 'Subway',
    agency_name: 'Metro İstanbul',
    mode: 'metro',
    ...over,
  };
}

// Mock — RouteStore.add() Map'i kullanır ama registerSummaries/getMeta
// zincirinde MapLibre dokunulmaz. Tip uyumu için cast yeter.
const stubMap = {} as MapLibreMap;

describe('RouteStore.registerSummaries / getMeta', () => {
  it('returns null before any summaries registered', () => {
    const rs = new RouteStore(stubMap);
    expect(rs.getMeta('public:m2')).toBeNull();
  });

  it('returns the summary for a registered route_id (single batch)', () => {
    const rs = new RouteStore(stubMap);
    rs.registerSummaries([summary()]);
    expect(rs.getMeta('public:m2')?.short_name).toBe('M2');
  });

  // KM-d.2 fix (Spec Ek A.19 borç #6): ferry summaries de RouteStore'a
  // beslenmeli. Önceki main.ts loadAlwaysVisibleRoutes sadece polyline
  // modlar için registerSummaries çağırıyordu, ferry route_id metadata
  // bulunamıyor → vehicle_popup "Hat metadata bulunamadı" fallback'ı.
  it('merges multiple registerSummaries calls (polyline + ferry)', () => {
    const rs = new RouteStore(stubMap);
    rs.registerSummaries([summary()]);
    rs.registerSummaries([
      summary({
        id: 2,
        route_id: 'public:f1',
        short_name: 'F1',
        long_name: 'BEŞİKTAŞ - ÜSKÜDAR',
        route_type: 4,
        route_type_label: 'Ferry',
        agency_name: 'Şehir Hatları A.Ş.',
        mode: 'ferry',
      }),
    ]);
    expect(rs.getMeta('public:m2')?.short_name).toBe('M2');
    expect(rs.getMeta('public:f1')?.agency_name).toBe('Şehir Hatları A.Ş.');
    expect(rs.getMeta('public:f1')?.mode).toBe('ferry');
  });

  it('returns null for unknown route_id even after registration', () => {
    const rs = new RouteStore(stubMap);
    rs.registerSummaries([summary()]);
    expect(rs.getMeta('public:never')).toBeNull();
  });
});
