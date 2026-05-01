// Faz 6 KM1 alt-iş f-6 — iki MapLibre filter expression'ını
// `['all', a, b]` olarak birleştirir. scheduled-circles layer'ı
// hem mode_visibility (alt-iş e) hem route_visibility (alt-iş f)
// filtresine tabidir; MapLibre tek filter desteklediği için
// composite gerekli.
//
// Edge case'ler:
//   - Her iki filter null (her ikisi no-op): null döner — caller
//     map.setFilter(layerId, null) ile tüm filtreleri kaldırır.
//   - Tek taraf null: dolu olan döner (gereksiz `['all']` sarmasız).
//   - İkisi dolu: `['all', a, b]`.

type Filter = unknown;

export function combineFilters(a: Filter | null, b: Filter | null): Filter | null {
  if (a === null && b === null) return null;
  if (a === null) return b;
  if (b === null) return a;
  return ['all', a, b];
}
