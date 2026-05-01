// Hat-bazlı kurumsal renk haritası (Faz 6 KM1 alt-iş a).
//
// İBB GTFS feed'leri renk metadata'sı yayınlamıyor: public feed'in
// route.color kolonu boş (Faz 1, spec §A.10), İETT feed'inde kolon
// hiç yok. Kanonik renkler manuel hardcode edilir.
//
// Birincil kaynak: Wikipedia "Module:Adjacent_stations/Istanbul_Metro"
//   https://en.wikipedia.org/wiki/Module:Adjacent_stations/Istanbul_Metro
// Bu modül istasyon diagramları için kullanılan kanonik hex tablosu.
//
// İkincil kaynak (mod fallback): İBB / Şehir Hatları kurumsal kimlik —
// hex teyidi tam doğrulanmadı; aşağıda yorumda işaretli.

export const ROUTE_COLORS: Record<string, string> = {
  // --- Metro İstanbul (kaynak: Wikipedia Lua modülü) ---
  // M1A ve M1B aynı operatör hattı (M1) — Wikipedia / Wikidata
  // (Q6048705) / metro.istanbul ağ haritası ikisini de aynı
  // kırmızı kullanır.
  'M1A': '#EE2229',
  'M1B': '#EE2229',
  'M2':  '#059A4D',
  'M3':  '#0CA6DF',
  'M4':  '#E81E77',
  'M5':  '#683166',
  'M6':  '#C9AA79',
  'M7':  '#F490B3',
  'M8':  '#487ABF',
  'M9':  '#FCD10D',
  'M10': '#4CAA3C',
  'M11': '#A1609B',
  'M12': '#CAD300',
  'M13': '#FF4B58',
  'M14': '#B16400',

  // --- Tramvay (kaynak: aynı Wikipedia modülü) ---
  // T2 ve T3 modülde yok — TODO: kaynak doğrulaması bekliyor,
  // şimdilik tram fallback'ine düşer.
  'T1': '#004B86',
  'T4': '#FF7E42',
  'T5': '#7B72B2',
  'T6': '#E77C7C',

  // --- Marmaray (kanonik turkuaz; metro.istanbul renk simgesi
  //     ve yaygın B1 logosundan) ---
  // TODO: hex değerini İBB Marmaray kurumsal kimlik dokümanıyla
  // birebir doğrula. Şimdilik makul tahmin.
  'MARMARAY':  '#00B7CD',
  'MARMARAY1': '#00B7CD',
  'MARMARAY2': '#00B7CD',

  // --- Funicular (F1, F2, F3, F4) ---
  // Wikipedia modülü F-hatlarını tek "kahverengi" altında topluyor;
  // metro.istanbul'da her F'in farklı bir vurgu rengi var (F1
  // turuncu Kabataş-Taksim, F4 gri Vialand vb.). TODO: per-line
  // hex doğrulaması — şimdilik funicular mod fallback'ine düşer.
};

// Mod-bazlı fallback (renk haritasında olmayan hatlar için).
// Faz 4 KM3 polyline paletiyle hizalı.
export const MODE_FALLBACK_COLORS: Record<string, string> = {
  metro:     '#1e40af',  // lacivert
  marmaray:  '#00B7CD',  // turkuaz (yukarıdaki Marmaray ile tutarlı)
  tram:      '#16a34a',  // yeşil
  funicular: '#ea580c',  // turuncu
  ferry:     '#003E7E',  // Şehir Hatları lacivert — TODO: resmi
                         // kurumsal kimlik dokümanıyla teyit et
  bus:       '#FDC70C',  // İBB belediye sarısı — TODO: kurumsal
                         // kimlik kılavuzu hex'ini birebir doğrula
                         // (sehirhatlari.istanbul logo turuncu/beyaz
                         // gemiler ve İBB sarısı yaygın söylem)
};

const DEFAULT_FALLBACK = '#6b7280'; // slate-500 — bilinmeyen mod

/**
 * Hat short_name + mode için kurumsal hex döndürür.
 * Önce ROUTE_COLORS (uppercase + trim normalize), yoksa
 * MODE_FALLBACK_COLORS, o da yoksa DEFAULT_FALLBACK.
 *
 * @example getRouteColor('M2', 'metro') → '#059A4D'
 * @example getRouteColor('m2', 'metro') → '#059A4D' (normalize)
 * @example getRouteColor('29B', 'bus') → '#FDC70C' (mod fallback)
 */
export function getRouteColor(shortName: string, mode: string): string {
  const key = (shortName ?? '').trim().toUpperCase();
  if (key in ROUTE_COLORS) return ROUTE_COLORS[key];
  const m = (mode ?? '').trim().toLowerCase();
  if (m in MODE_FALLBACK_COLORS) return MODE_FALLBACK_COLORS[m];
  return DEFAULT_FALLBACK;
}

// --- HSL color manipulation -------------------------------------------------

type RGB = readonly [number, number, number];
type HSL = readonly [number, number, number]; // h, s, l ∈ [0, 1]

function hexToRgb(hex: string): RGB {
  const h = hex.startsWith('#') ? hex.slice(1) : hex;
  return [
    parseInt(h.slice(0, 2), 16),
    parseInt(h.slice(2, 4), 16),
    parseInt(h.slice(4, 6), 16),
  ];
}

function rgbToHex([r, g, b]: RGB): string {
  const c = (n: number) => n.toString(16).padStart(2, '0').toUpperCase();
  return `#${c(r)}${c(g)}${c(b)}`;
}

function rgbToHsl([r, g, b]: RGB): HSL {
  const rn = r / 255;
  const gn = g / 255;
  const bn = b / 255;
  const max = Math.max(rn, gn, bn);
  const min = Math.min(rn, gn, bn);
  const l = (max + min) / 2;
  if (max === min) return [0, 0, l];
  const d = max - min;
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
  let h = 0;
  if (max === rn) h = (gn - bn) / d + (gn < bn ? 6 : 0);
  else if (max === gn) h = (bn - rn) / d + 2;
  else h = (rn - gn) / d + 4;
  h /= 6;
  return [h, s, l];
}

function hslToRgb([h, s, l]: HSL): RGB {
  if (s === 0) {
    const v = Math.round(l * 255);
    return [v, v, v];
  }
  const hue2rgb = (p: number, q: number, t: number): number => {
    if (t < 0) t += 1;
    if (t > 1) t -= 1;
    if (t < 1 / 6) return p + (q - p) * 6 * t;
    if (t < 1 / 2) return q;
    if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6;
    return p;
  };
  const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
  const p = 2 * l - q;
  return [
    Math.round(hue2rgb(p, q, h + 1 / 3) * 255),
    Math.round(hue2rgb(p, q, h) * 255),
    Math.round(hue2rgb(p, q, h - 1 / 3) * 255),
  ];
}

/**
 * Hex rengin HSL uzayında L değerini `amount` kadar artırır
 * (clamp [0, 1]). Scheduled vehicle dot'larının polyline
 * üzerinde "açık ton" görünmesi için kullanılacak (alt-iş c).
 *
 * @example lighten('#009E4F', 0.2) → daha açık yeşil
 * @example lighten('#000000', 0.5) → '#808080' (mid-gray)
 */
export function lighten(hex: string, amount: number): string {
  const rgb = hexToRgb(hex);
  const [h, s, l] = rgbToHsl(rgb);
  const newL = Math.min(1, Math.max(0, l + amount));
  return rgbToHex(hslToRgb([h, s, newL]));
}
