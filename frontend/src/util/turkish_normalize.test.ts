import { describe, expect, it } from 'vitest';
import { fuzzyMatch, isMojibake, normalize } from './turkish_normalize';

describe('normalize', () => {
  it('lowercases İETT to iett (İ → i)', () => {
    expect(normalize('İETT')).toBe('iett');
  });

  it('strips Turkish diacritics in a multi-letter compound', () => {
    expect(normalize('Şişhane-Hacıosman')).toBe('sishane-haciosman');
  });

  it('lowercases plain ASCII without changes', () => {
    expect(normalize('GAYRETTEPE')).toBe('gayrettepe');
  });

  it('handles Üsküdar → uskudar', () => {
    expect(normalize('Üsküdar')).toBe('uskudar');
  });

  it('handles Çamlıca → camlica', () => {
    expect(normalize('Çamlıca')).toBe('camlica');
  });

  it('returns empty string for empty input', () => {
    expect(normalize('')).toBe('');
  });

  it('preserves digits in alphanumeric route codes', () => {
    expect(normalize('29B')).toBe('29b');
  });

  it('lowercases simple route code M2', () => {
    expect(normalize('M2')).toBe('m2');
  });

  it('handles every Turkish-specific letter pair (round-trip sanity)', () => {
    expect(normalize('İIıŞşĞğÜüÖöÇç')).toBe('iiissgguuoocc');
  });

  it('does not collapse non-Turkish unicode (latin a-acute survives lowercase)', () => {
    expect(normalize('Á')).toBe('á');
  });
});

describe('fuzzyMatch', () => {
  it('matches lowercase digits-letters against uppercase', () => {
    expect(fuzzyMatch('29b', '29B')).toBe(true);
  });

  it('matches a Turkish prefix against a Turkish target', () => {
    expect(fuzzyMatch('Şiş', 'Şişhane')).toBe(true);
  });

  it('matches an ASCII transliteration of a Turkish target', () => {
    expect(fuzzyMatch('siş', 'Şişhane')).toBe(true);
  });

  it('returns false when there is no substring match', () => {
    expect(fuzzyMatch('xyz', 'M2')).toBe(false);
  });

  it('empty query matches everything (UX: empty search shows all)', () => {
    expect(fuzzyMatch('', 'herhangi bir')).toBe(true);
  });

  it('matches a substring inside a long route name', () => {
    expect(fuzzyMatch('m2', 'M2 - Yenikapı-Hacıosman')).toBe(true);
  });

  it('matches a Turkish-letter prefix (hac → Hacıosman)', () => {
    expect(fuzzyMatch('hac', 'Hacıosman')).toBe(true);
  });

  it('case + diacritic insensitive (USKUDAR query → üsküdar target)', () => {
    expect(fuzzyMatch('USKUDAR', 'üsküdar')).toBe(true);
  });

  it('matches a digit substring inside an alphanumeric route', () => {
    expect(fuzzyMatch('29', '129BS')).toBe(true);
  });

  it('non-empty query against empty target → false', () => {
    expect(fuzzyMatch('xx', '')).toBe(false);
  });
});

describe('isMojibake', () => {
  it('returns false for clean Turkish', () => {
    expect(isMojibake('KADIKÖY - KİRAZLITEPE')).toBe(false);
    expect(isMojibake('Şişhane-Hacıosman')).toBe(false);
  });

  it('detects U+FFFD replacement character', () => {
    expect(isMojibake('ATA�EHİR')).toBe(true);
  });

  it('detects double-encoded UTF-8 sequence (Ã + diacritic)', () => {
    expect(isMojibake('Ã–STÜN')).toBe(true);
    expect(isMojibake('KÄ°RAZLITEPE')).toBe(true);
  });

  it('does not flag Portuguese "São Paulo" (Ã + ASCII o)', () => {
    expect(isMojibake('São Paulo')).toBe(false);
  });

  it('returns false for ASCII / pure-Latin input', () => {
    expect(isMojibake('M2')).toBe(false);
    expect(isMojibake('')).toBe(false);
    expect(isMojibake('Yenikapi')).toBe(false);
  });

  it('detects D-stroke (Đ) — non-Turkish Latin Extended marker', () => {
    expect(isMojibake('ATAĐĐEHÄºR TIP MERKEZÄº')).toBe(true);
  });

  it('detects thorn (Þ) — non-Turkish Latin Extended marker', () => {
    expect(isMojibake('ÞESATPAÅA')).toBe(true);
  });

  it('does not flag clean Turkish text without non-Turkish Latin Extended', () => {
    expect(isMojibake('Şişli Mecidiyeköy')).toBe(false);
    expect(isMojibake('Üsküdar - Ümraniye')).toBe(false);
    expect(isMojibake('ATAŞEHİR TIP MERKEZİ - ESATPAŞA')).toBe(false);
  });
});
