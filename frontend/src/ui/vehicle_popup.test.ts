import { describe, expect, it } from 'vitest';
import { buildPopupHtml, escapeHtml } from './vehicle_popup';
import type { RouteSummary } from '../data/api';

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

describe('buildPopupHtml — scheduled with metadata', () => {
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
    // Internal IDs gizli
    expect(html).not.toContain('953563');
    expect(html).not.toContain('public:m2');
  });

  it('falls back to "Hat metadata bulunamadı" when meta is null', () => {
    const html = buildPopupHtml({ route_id: 'public:m2' }, 'scheduled', null);
    expect(html).toContain('Hat metadata bulunamadı');
  });

  it('marks mojibake long_name with ⚠', () => {
    const html = buildPopupHtml(
      { route_id: 'iett:x' },
      'scheduled',
      meta({ short_name: 'X', long_name: 'KÄ°RAZLITEPE - ARDA' }),
    );
    expect(html).toContain('⚠');
  });
});

describe('buildPopupHtml — iett mapped', () => {
  it('renders short_name + long_name + agency_name + KapiNo', () => {
    const html = buildPopupHtml(
      { id: 'C-231', route_id: 'iett:29B' },
      'iett',
      meta({ short_name: '29B', long_name: 'ECLİPSE SİTESİ - FATİH', agency_name: 'IETT' }),
    );
    expect(html).toContain('29B');
    expect(html).toContain('ECLİPSE SİTESİ - FATİH');
    expect(html).toContain('IETT');
    expect(html).toContain('KapiNo:');
    expect(html).toContain('C-231');
    expect(html).toContain('İETT canlı');
  });
});

describe('buildPopupHtml — iett unmapped', () => {
  it('renders KapiNo + "Hat bilinmiyor" when meta is null', () => {
    const html = buildPopupHtml({ id: 'C-999' }, 'iett', null);
    expect(html).toContain('KapiNo:');
    expect(html).toContain('C-999');
    expect(html).toContain('Hat bilinmiyor');
  });

  it('escapes hostile KapiNo (XSS guard)', () => {
    const html = buildPopupHtml({ id: '<img src=x>' }, 'iett', null);
    expect(html).not.toContain('<img');
    expect(html).toContain('&lt;img');
  });
});
