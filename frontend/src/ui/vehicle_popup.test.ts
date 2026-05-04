import { describe, expect, it } from 'vitest';
import { buildPopupHtml, escapeHtml, type ScheduledPopupContext } from './vehicle_popup';
import type { RouteSummary } from '../data/api';
import type { PreparedTrip } from '../simulation/scheduled_trip';

function meta(over: Partial<RouteSummary> = {}): RouteSummary {
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

function preparedTrip(
  projections: { sec: number; name: string; seq: number }[],
): PreparedTrip {
  return {
    trip_id: 't1',
    route_id: 'public:m2',
    short_name: 'M2',
    direction_id: 0,
    mode: 'metro',
    polyline: [[29.0, 41.0], [29.0, 41.01]],
    cumDist: [0, 1110],
    stopProjections: projections.map((p) => ({
      arrivalSec: p.sec,
      arcLengthM: 0,
      stopName: p.name,
      sequence: p.seq,
    })),
    firstArrSec: projections[0]?.sec ?? 0,
    lastArrSec: projections[projections.length - 1]?.sec ?? 0,
  };
}

function ctx(prepared: PreparedTrip | null, nowSec: number): ScheduledPopupContext {
  return { nowSec, prepared };
}

describe('escapeHtml', () => {
  it('escapes the five HTML-significant characters', () => {
    expect(escapeHtml(`<script>alert("&'")</script>`)).toBe(
      '&lt;script&gt;alert(&quot;&amp;&#39;&quot;)&lt;/script&gt;',
    );
  });

  it('returns plain text unchanged', () => {
    expect(escapeHtml('M2')).toBe('M2');
  });
});

describe('buildPopupHtml — iett bus minimal (KM5-d)', () => {
  it('renders "İETT Otobüs" label + KapiNo, no route metadata', () => {
    const html = buildPopupHtml({ id: 'C-231', route_id: 'iett:any' }, 'iett', meta());
    expect(html).toContain('İETT Otobüs');
    expect(html).toContain('KapiNo:');
    expect(html).toContain('C-231');
    expect(html).toContain('İETT canlı');
    // Hat etiketleri / uyarı mesajları artık görünmemeli (KM5-d kararı).
    expect(html).not.toContain('M2');
    expect(html).not.toContain('YENİKAPI');
    expect(html).not.toContain('henüz hat eşlemesi');
    expect(html).not.toContain('mapping pipeline');
  });

  it('uses minimal layout regardless of meta presence (mapping retired)', () => {
    const withMeta = buildPopupHtml({ id: 'B-1' }, 'iett', meta());
    const withoutMeta = buildPopupHtml({ id: 'B-1' }, 'iett', null);
    // Aynı KapiNo + meta yokluğu/varlığı → aynı sade çıktı (mapping
    // sözleşmesi v0.8.0'da kapalı, meta render edilmiyor).
    expect(withMeta).toBe(withoutMeta);
  });

  it('escapes hostile KapiNo (XSS guard)', () => {
    const html = buildPopupHtml({ id: '<img src=x>' }, 'iett', null);
    expect(html).not.toContain('<img');
    expect(html).toContain('&lt;img');
  });

  it('handles missing KapiNo (defensive ?)', () => {
    const html = buildPopupHtml({}, 'iett', null);
    expect(html).toContain('KapiNo: <b>?</b>');
  });
});

describe('buildPopupHtml — scheduled with metadata, no context', () => {
  it('renders short_name + long_name + agency_name (no internal IDs)', () => {
    const html = buildPopupHtml(
      { trip_id: '953563', route_id: 'public:m2', mode: 'metro' },
      'scheduled',
      meta(),
    );
    expect(html).toContain('M2');
    expect(html).toContain('YENİKAPI - HACIOSMAN');
    expect(html).toContain('Metro İstanbul');
    expect(html).toContain('Tarife-bazlı simülasyon');
    expect(html).not.toContain('953563');
    expect(html).not.toContain('public:m2');
    // context vermeden next_stops bloğu render edilmemeli
    expect(html).not.toContain('Sonraki duraklar');
  });

  it('falls back to "Hat metadata bulunamadı" when meta is null', () => {
    const html = buildPopupHtml({ route_id: 'public:m2' }, 'scheduled', null);
    expect(html).toContain('Hat metadata bulunamadı');
    expect(html).not.toContain('Sonraki duraklar');
  });

  it('marks mojibake long_name with ⚠ and hides the corrupted text (KM-c.1)', () => {
    const html = buildPopupHtml(
      { route_id: 'iett:x' },
      'scheduled',
      meta({ short_name: 'X', long_name: 'KÄ°RAZLITEPE - ARDA' }),
    );
    expect(html).toContain('⚠');
    expect(html).toContain('Hat adı okunamıyor');
    // Bozuk metnin kendisi popup'ta görünmemeli — Yağız smoke (Ek A.19 #3).
    expect(html).not.toContain('KÄ°RAZLITEPE');
    expect(html).not.toContain('ARDA');
  });

  it('renders clean long_name unchanged when not mojibake (regression)', () => {
    const html = buildPopupHtml(
      { route_id: 'public:m2' },
      'scheduled',
      meta(),
    );
    expect(html).toContain('YENİKAPI - HACIOSMAN');
    expect(html).not.toContain('⚠');
    expect(html).not.toContain('Hat adı okunamıyor');
  });
});

describe('buildPopupHtml — iett popup metrobüs label (KM-c.2)', () => {
  it('renders "Metrobüs" label when is_metrobus=true', () => {
    const html = buildPopupHtml({ id: 'M-42', is_metrobus: true }, 'iett', null);
    expect(html).toContain('Metrobüs');
    expect(html).not.toContain('İETT Otobüs');
    expect(html).toContain('KapiNo:');
    expect(html).toContain('M-42');
  });

  it('renders "İETT Otobüs" label when is_metrobus=false', () => {
    const html = buildPopupHtml({ id: 'B-1', is_metrobus: false }, 'iett', null);
    expect(html).toContain('İETT Otobüs');
    expect(html).not.toContain('Metrobüs');
  });

  it('renders "İETT Otobüs" label when is_metrobus is undefined (regression)', () => {
    const html = buildPopupHtml({ id: 'B-1' }, 'iett', null);
    expect(html).toContain('İETT Otobüs');
    expect(html).not.toContain('Metrobüs');
  });
});

describe('buildPopupHtml — scheduled rich (next_stops, KM5-d)', () => {
  it('renders next 5 stops with name + scheduled + eta', () => {
    const prep = preparedTrip([
      { sec: 36000, name: 'Şişli-Mecidiyeköy', seq: 1 },
      { sec: 36120, name: 'Gayrettepe', seq: 2 },
      { sec: 36300, name: 'Levent', seq: 3 },
      { sec: 36480, name: '4.Levent', seq: 4 },
      { sec: 36660, name: 'Sanayi', seq: 5 },
      { sec: 36840, name: 'İTÜ-Ayazağa', seq: 6 },
    ]);
    const html = buildPopupHtml(
      { trip_id: 't1', route_id: 'public:m2', mode: 'metro' },
      'scheduled',
      meta(),
      ctx(prep, 35900),
    );
    expect(html).toContain('Sonraki duraklar');
    expect(html).toContain('Şişli-Mecidiyeköy');
    expect(html).toContain('Gayrettepe');
    expect(html).toContain('Levent');
    expect(html).toContain('4.Levent');
    expect(html).toContain('Sanayi');
    // Limit 5: 6. durak görünmemeli
    expect(html).not.toContain('İTÜ-Ayazağa');
    // Planlı saat formatı
    expect(html).toContain('10:00');
    // ETA formatı (35900 → 36000 = 100sn ≈ 2 dk yuvarlanır)
    expect(html).toContain('2 dk');
  });

  it('shows "Sonraki durak yok (terminus)" when all stops are past', () => {
    const prep = preparedTrip([
      { sec: 36000, name: 'A', seq: 1 },
      { sec: 36060, name: 'B', seq: 2 },
    ]);
    const html = buildPopupHtml(
      { trip_id: 't1', route_id: 'public:m2', mode: 'metro' },
      'scheduled',
      meta(),
      ctx(prep, 99999),
    );
    expect(html).toContain('Sonraki duraklar');
    expect(html).toContain('terminus');
    expect(html).not.toContain('vehicle-popup__stop-name">A<');
  });

  it('omits next_stops block when context.prepared is null', () => {
    const html = buildPopupHtml(
      { trip_id: 't1', route_id: 'public:m2', mode: 'metro' },
      'scheduled',
      meta(),
      ctx(null, 36000),
    );
    expect(html).toContain('M2');
    expect(html).toContain('Metro İstanbul');
    expect(html).not.toContain('Sonraki duraklar');
  });

  it('escapes hostile stopName (XSS guard)', () => {
    const prep = preparedTrip([
      { sec: 36000, name: '<img src=x>', seq: 1 },
      { sec: 36060, name: 'B', seq: 2 },
    ]);
    const html = buildPopupHtml(
      { trip_id: 't1', route_id: 'public:m2', mode: 'metro' },
      'scheduled',
      meta(),
      ctx(prep, 35900),
    );
    expect(html).not.toContain('<img');
    expect(html).toContain('&lt;img');
  });
});
