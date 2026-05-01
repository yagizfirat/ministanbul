// Route panel item flattening — varyant gruplaması ve search filtre
// (Faz 6 KM1 alt-iş f-polish-2 madde 3).
//
// İBB iETT feed'inde aynı `short_name` (örn. "29B") 7+ ayrı route_id
// olarak gelir (yön + uç-nokta varyantları). Panel'de her satır olarak
// göstermek bunaltıcı — tek başlık + expandable body modeline geçiyoruz.
//
// Saf fonksiyon: input (routes, expandedGroups, searchQuery) → output
// FlatItem[]. Hem polyline modların DOM render'ı hem bus'ın virtual_list
// setItems çağrısı aynı dizilimi tüketir.

import type { RouteSummary } from '../data/api';
import { fuzzyMatch } from '../util/turkish_normalize';

export type FlatItem =
  | { kind: 'single'; route: RouteSummary }
  | { kind: 'group-header'; shortName: string; mode: string; variants: RouteSummary[] }
  | {
      kind: 'group-variant';
      route: RouteSummary;
      parentShortName: string;
      // f-polish-5: variant satırı uzun isim/operatör göstermez,
      // sıralı "Araç 1, Araç 2, ..." labelları kullanır.
      displayLabel: string;
    };

// `expandedGroups` key formatı: `${mode}|${shortName}` (mod-altında çakışma önler).
export function expandedKey(mode: string, shortName: string): string {
  return `${mode}|${shortName}`;
}

function matches(query: string, route: RouteSummary): boolean {
  if (query === '') return true;
  return fuzzyMatch(query, route.short_name) || fuzzyMatch(query, route.long_name);
}

/**
 * Routes'u short_name bazında grupla, search filter uygula, expandedGroups
 * state'ine göre flatten et.
 *
 * Davranış:
 *   - Tek-variant grup → 'single' satır (group header yok).
 *   - Çoklu-variant grup:
 *     - Search inactive: header satırı + (expanded ise variant'lar)
 *     - Search active: header satırı görünür ↔ short_name match VEYA
 *       variant'lardan en az biri match. Match olan variant'ın varsa
 *       parent header **otomatik expand** edilir (expandedGroups'a
 *       runtime'da eklenir, persist etmez).
 */
export function flattenRoutesForDisplay(
  routes: readonly RouteSummary[],
  expandedGroups: ReadonlySet<string>,
  searchQuery: string,
): FlatItem[] {
  // 1) short_name → variants
  const groups = new Map<string, RouteSummary[]>();
  for (const r of routes) {
    const key = (r.short_name || r.route_id).trim();
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)!.push(r);
  }

  const out: FlatItem[] = [];
  const searchActive = searchQuery !== '';

  for (const [shortName, variants] of groups) {
    const mode = variants[0].mode;
    const groupKey = expandedKey(mode, shortName);

    // Search filter — variant ve header düzeyinde
    const variantMatches = variants.map((v) => matches(searchQuery, v));
    const anyVariantMatch = variantMatches.some(Boolean);
    const headerNameMatches = !searchActive || fuzzyMatch(searchQuery, shortName);

    // Search active'de header görünmesi için: name match VEYA variant match.
    // Search inactive'de her zaman görünür.
    const headerVisible = !searchActive || headerNameMatches || anyVariantMatch;
    if (!headerVisible) continue;

    if (variants.length === 1) {
      // Tek variant — group header yok, düz single item.
      // Search active'de variant match yoksa atla.
      if (!searchActive || variantMatches[0] || headerNameMatches) {
        out.push({ kind: 'single', route: variants[0] });
      }
      continue;
    }

    // Çoklu variant
    out.push({ kind: 'group-header', shortName, mode, variants });

    // Body görünür mü:
    //   - explicitly expanded
    //   - search active + bir variant query'ye match → auto-expand
    const autoExpand = searchActive && anyVariantMatch && !headerNameMatches;
    const bodyVisible = expandedGroups.has(groupKey) || autoExpand;
    if (!bodyVisible) continue;

    // f-polish-5: variant'ları route_id alfabetik sırayla "Araç N"
    // labelı ile döndür. Sort hem deterministic numbering hem
    // search match subset'inin nasıl göründüğünü stabilize eder.
    const sorted = [...variants]
      .map((route, originalIdx) => ({ route, originalIdx }))
      .sort((a, b) => a.route.route_id.localeCompare(b.route.route_id));
    sorted.forEach(({ route, originalIdx }, sortedIdx) => {
      if (!searchActive || variantMatches[originalIdx] || headerNameMatches) {
        out.push({
          kind: 'group-variant',
          route,
          parentShortName: shortName,
          displayLabel: `Araç ${sortedIdx + 1}`,
        });
      }
    });
  }

  return out;
}
