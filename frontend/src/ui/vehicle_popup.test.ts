import { describe, expect, it } from 'vitest';
import { buildPopupHtml, escapeHtml } from './vehicle_popup';

describe('escapeHtml', () => {
  it('escapes the five HTML-significant characters', () => {
    expect(escapeHtml(`<script>alert("&'")</script>`)).toBe(
      '&lt;script&gt;alert(&quot;&amp;&#39;&quot;)&lt;/script&gt;',
    );
  });

  it('returns plain text unchanged', () => {
    expect(escapeHtml('M2')).toBe('M2');
    expect(escapeHtml('')).toBe('');
  });
});

describe('buildPopupHtml — iett source', () => {
  it('includes KapiNo + mapped hat short_name', () => {
    const html = buildPopupHtml(
      { id: 'C-231', route_id: 'iett:29B', short_name: '29B' },
      'iett',
    );
    expect(html).toContain('KapiNo:');
    expect(html).toContain('C-231');
    expect(html).toContain('29B');
    expect(html).toContain('İETT canlı');
  });

  it('shows "Hat bilinmiyor" when route_id is missing (unmapped vehicle)', () => {
    const html = buildPopupHtml({ id: 'C-999' }, 'iett');
    expect(html).toContain('Hat bilinmiyor');
    expect(html).not.toContain('Hat: <b>');
  });

  it('escapes hostile KapiNo (XSS guard)', () => {
    const html = buildPopupHtml({ id: '<img src=x>' }, 'iett');
    expect(html).not.toContain('<img');
    expect(html).toContain('&lt;img');
  });
});

describe('buildPopupHtml — scheduled source', () => {
  it('includes trip + hat + mod + simulation note', () => {
    const html = buildPopupHtml(
      { trip_id: 'tx-1', route_id: 'public:m2', short_name: 'M2', mode: 'metro' },
      'scheduled',
    );
    expect(html).toContain('Trip:');
    expect(html).toContain('tx-1');
    expect(html).toContain('M2');
    expect(html).toContain('metro');
    expect(html).toContain('Tarife-bazlı simülasyon');
  });

  it('renders ⚠ marker when short_name is mojibake', () => {
    const html = buildPopupHtml(
      { trip_id: 't1', short_name: 'KÄ°RAZLITEPE', mode: 'bus' },
      'scheduled',
    );
    expect(html).toContain('⚠');
  });
});
