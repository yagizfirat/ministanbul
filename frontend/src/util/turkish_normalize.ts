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
