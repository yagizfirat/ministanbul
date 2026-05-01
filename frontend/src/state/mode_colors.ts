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

// Scheduled vehicle dot colors — distinct from polyline colors so a moving
// vehicle stays visible against its own line. Pastel fill + saturated stroke.
export const SCHEDULED_VEHICLE_COLORS: Record<string, { fill: string; stroke: string }> = {
  metro:     { fill: '#60a5fa', stroke: '#1e3a8a' }, // blue-400 / blue-900
  marmaray:  { fill: '#c084fc', stroke: '#6b21a8' }, // purple-400 / purple-800
  tram:      { fill: '#4ade80', stroke: '#166534' }, // green-400 / green-800
  funicular: { fill: '#fb923c', stroke: '#9a3412' }, // orange-400 / orange-800
  ferry:     { fill: '#22d3ee', stroke: '#155e75' }, // cyan-400 / cyan-800
};

export const SCHEDULED_VEHICLE_FALLBACK = { fill: '#9ca3af', stroke: '#374151' };
