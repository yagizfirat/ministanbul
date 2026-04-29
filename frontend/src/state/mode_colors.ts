// Hardcoded mode → hex color map.
// İBB feed routes carry route.color but values are '#000000' or unset
// (spec Ek A.10), so the frontend owns the color story. KM6 panel and
// KM5 metrobus snapping consume this same map.

const MODE_COLORS: Record<string, string> = {
  metro:     '#1e40af',
  marmaray:  '#4338ca',
  tram:      '#16a34a',
  funicular: '#ea580c',
  ferry:     '#0891b2',
  metrobus:  '#b91c1c',
  bus:       '#6b7280',
};

const FALLBACK = '#6b7280';

export function colorForMode(mode: string): string {
  return MODE_COLORS[mode] ?? FALLBACK;
}
