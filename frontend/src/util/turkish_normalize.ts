// Türkçe diakritikleri Latin karşılığa indir + lowercase. Hat
// arama için (Faz 6 KM1 alt-iş f-3): "şiş" "Şişhane" ile,
// "29b" "29B" ile, "USKUDAR" "Üsküdar" ile match etmeli.
//
// Intl.Collator ve String.prototype.normalize('NFD') Türkçe için
// yanlış sonuçlar üretir (İ/ı ayrımı kaybolur). Manuel char-map
// deterministik ve hızlı.

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
  // for…of iterates code points; BMP karakterler için davranış
  // toplama operatörüyle aynı, gelecekteki surrogate-pair (emoji)
  // içeriklere karşı güvenli.
  for (const ch of s) {
    out += TR_MAP[ch] ?? ch.toLowerCase();
  }
  return out;
}

export function fuzzyMatch(query: string, target: string): boolean {
  if (query === '') return true; // boş arama → tüm hedefler match
  return normalize(target).includes(normalize(query));
}

// Backend `import_gtfs._demojibake` iETT routes'larının ~%76'sını
// kurtardı (f-polish-4 hibrit pass). Kalan ~%24'te ya U+FFFD ya da
// karışık byte sequence (cp1252-undefined + utf-8 karması) — kaynakta
// kurtarılamaz. Frontend bu kalanları UI'da uyarı ikonuyla işaretler.
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
