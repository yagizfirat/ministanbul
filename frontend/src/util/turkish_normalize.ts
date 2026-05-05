// Turkish-aware lowercase + diacritic folding for the route search box.
// Goal: "şiş" matches "Şişhane", "29b" matches "29B", "USKUDAR"
// matches "Üsküdar".
//
// Intl.Collator and String.prototype.normalize('NFD') misbehave for
// Turkish (they collapse the İ/ı distinction), so we use an explicit
// char-map — deterministic and faster.

const TR_MAP: Record<string, string> = {
  'İ': 'i', 'I': 'i', 'ı': 'i',
  'Ş': 's', 'ş': 's',
  'Ğ': 'g', 'ğ': 'g',
  'Ü': 'u', 'ü': 'u',
  'Ö': 'o', 'ö': 'o',
  'Ç': 'c', 'ç': 'c',
};

export function normalize(s: string): string {
  let out = '';
  // for…of iterates by code point — surrogate-safe for future emoji.
  for (const ch of s) {
    out += TR_MAP[ch] ?? ch.toLowerCase();
  }
  return out;
}

export function fuzzyMatch(query: string, target: string): boolean {
  if (query === '') return true;
  return normalize(target).includes(normalize(query));
}

// The backend's GTFS demojibake pass recovers most İETT route names,
// but a residual fraction stays broken (mixed cp1252/utf-8 byte
// sequences or U+FFFD replacement chars are unrecoverable at source).
// The frontend flags those rows in the UI with a warning icon.
//
// Üç indikatör:
//   1. U+FFFD replacement char doğrudan
//   2. Ã/Ä/Å + Latin-1 Supplement / General Punctuation: double-encoded UTF-8
//   3. Türkçe-dışı Latin Extended karakterler (Đ/đ, Þ/þ, Æ/æ) —
//      Türkçe metinde geçmez, encoding mojibake göstergesi
//      (latin1↔utf-8 veya iso-8859-9 karması).
export function isMojibake(s: string): boolean {
  if (!s) return false;
  if (s.includes('�')) return true;
  if (/[ÃÄÅ][-ÿ -⁯]/.test(s)) return true;
  return /[ĐđÞþÆæ]/.test(s);
}
