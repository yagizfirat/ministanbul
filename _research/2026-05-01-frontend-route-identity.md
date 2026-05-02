# Frontend Route Identity Kontratı Keşfi (read-only)

Tarih: 2026-05-01
Kapsam: `frontend/src/` — backend ve API tarafı dışarıda. Sadece okuma; build/test çalıştırılmadı.

---

## Bölüm 1 — RouteStore key kontratı

**Bulgu:** `RouteStore` iç state'i `summariesByRouteId: Map<string, RouteSummary>` ve `entries: Map<string, RouteEntry>` olmak üzere iki map tutar; her iki map'in key'i de `RouteSummary.route_id` string field'ından üretilir (örn. `"public:m2"`, `"iett:1562"`). Short_name bazlı bir indeks yok.

`frontend/src/state/route_store.ts:16-29`:

```ts
export class RouteStore {
  private readonly map: MapLibreMap;
  private entries = new Map<string, RouteEntry>();
  private summariesByRouteId = new Map<string, RouteSummary>();
  ...
  registerSummaries(summaries: RouteSummary[]): void {
    for (const s of summaries) this.summariesByRouteId.set(s.route_id, s);
  }
```

Public API'nin tamamı route_id string'i alır: `getMeta(routeId)` (line 34), `has(routeId)` (38), `add(routeId)` (46), `remove(routeId)` (70). Variant `add` içinde line 50: `throw new Error(\`RouteStore.add(${routeId}): unknown route — call registerSummaries first\`)`.

Test fixture'ları doğrudan bu kontratı yansıtıyor. `frontend/src/ui/route_panel_flatten.test.ts:7-17`:

```ts
function r(over: Partial<RouteSummary> = {}): RouteSummary {
  return {
    id: 0,
    route_id: 'iett:1',
    short_name: '29B',
    ...
```

ve `frontend/src/ui/route_panel.test.ts:21-27`:

```ts
const SAMPLE_ROUTES: RouteSummary[] = [
  route({ id: 1, route_id: 'public:m1a', short_name: 'M1A', ... }),
  route({ id: 5, route_id: 'iett:29B', short_name: '29B', ..., mode: 'bus' }),
];
```

Fixture'larda key formatı her zaman `${prefix}:${suffix}` (public:|iett:); short_name ayrı field.

---

## Bölüm 2 — /api/routes/ response shape

**Bulgu:** Frontend `/api/routes/active/` endpoint'ini KULLANMIYOR. Bunun yerine DRF'in standart `/api/routes/?mode=...` paginated list endpoint'ini çağırır ve dönen Route object array'inin `route_id` field'ını `RouteSummary.route_id`'ye birebir kopyalar. Spec §6.3'ün bahsettiği `{categories: {bus: ["29B", ...]}}` şeklindeki short_name listesi frontend hiçbir yerde tüketilmiyor — doğrulanamadı: bu endpoint backend'de var mı yok mu, frontend tarafından bakılmıyor.

`frontend/src/data/api.ts:13-24` tip tanımı:

```ts
export interface RouteSummary {
  id: number;
  route_id: string;          // "public:1298" or "iett:NNNN"
  short_name: string;
  long_name: string;
  route_type: number;
  route_type_label: string;
  agency_name: string;
  mode: string;
}
```

Fetch çağrıları `fetchRoutesForMode` (line 117-134) ve `fetchAllBusRoutes` (line 98-115):

```ts
async function fetchRoutesForMode(mode: string): Promise<RouteSummary[]> {
  const url = `/api/routes/?mode=${encodeURIComponent(mode)}&has_shape=true&page_size=200`;
  ...
  return data.results.map((r) => ({
    id: r.id,
    route_id: r.route_id,
    short_name: r.short_name,
    ...
```

`BackendRoute` interface (line 73-81) backend response'undaki Route object'i tipler: `{ id, route_id, agency, short_name, long_name, route_type, route_type_label }`. `route_id` field'ı backend'den geldiği gibi (transformation'sız) `RouteSummary.route_id`'ye taşınır. RouteStore daha sonra bu field'ı key olarak kullanır (Bölüm 1).

---

## Bölüm 3 — Panel routeIds doğuş yeri

**Bulgu:** Panel'in tüm routeId çıktıları (checkbox toggle, bulk action, dblclick handler'ları) `allRoutes` array'i içindeki `RouteSummary` object'lerinin `route_id` field'ından doğar. Component state'inde alternatif id tutulmuyor; API response'undan gelen string doğrudan handler argümanı oluyor.

`frontend/src/ui/route_panel.ts` içindeki kritik handler'lar:

Single route checkbox (line 331-334):

```ts
cb.addEventListener('change', () => opts.visibility.toggle(route.route_id));
```

Single route dblclick (line 344-348):

```ts
el.addEventListener('dblclick', (e) => {
  e.stopPropagation();
  opts.onRouteDoubleClick?.(route.route_id);
});
```

Variant header — variant'ların id'leri toplu çıkarılır (line 371-378):

```ts
const ids = variants.map((v) => v.route_id);
const visibleCount = ids.filter((id) => opts.visibility.isVisible(id)).length;
cb.addEventListener('change', () => {
  ...
  opts.visibility.setBulkVisible(ids, !allVisible);
});
```

Variant header dblclick (line 395-398):

```ts
el.addEventListener('dblclick', (e) => {
  e.stopPropagation();
  opts.onVariantGroupDoubleClick?.(ids);
});
```

Bulk/group toggle (line 550-555): `const ids = routes.map((r) => r.route_id);`. SelectAll (line 557-559) ve SelectNone (562-564) aynı pattern.

`main.ts:210-211` panel çıktısını `focusAndZoom`'a yönlendirir:

```ts
onRouteDoubleClick: (routeId) => focusAndZoom([routeId]),
onVariantGroupDoubleClick: (routeIds) => focusAndZoom(routeIds),
```

`focusAndZoom` (main.ts:214-225) bu routeIds'i `RouteFocus.setFocus`, `getRoutesBBox`, `SnapshotStore.getVehicleBBoxForRoutes`'e geçirir — üçü de aynı `route_id` string'lerini bekler.

---

## Bölüm 4 — Polyline (shape) layer key kontratı

**Bulgu:** Polyline feature'ı hem `route_id` hem `short_name` field'larını taşır; layer'ın source ID'si `routes`, layer ID'si `route-lines`, glow layer'ı `route-lines-glow`. Shape fetch path'i `/api/routes/${routeId}/shape/` — yani backend Route lookup'ı PK-prefixed string ile (`iett:1562`), short_name ile değil. Polyline focus filter'ı `['in', ['get', 'route_id'], ['literal', focused]]` kullanır; focused dizisi de PK-formatlı route_id'ler içerdiği için polyline tarafında focus sessizce çalışır (mismatch yok).

`frontend/src/render/route_lines_layer.ts:9-19`:

```ts
interface RouteFeature {
  type: 'Feature';
  geometry: ShapeFeature['geometry'];
  properties: {
    route_id: string;
    shape_id: string;
    short_name: string;
    mode: string;
    color: string;
  };
}
```

Feature builder line 65-83 `buildRouteFeature(routeId, shortName, mode, color, shape)` — caller `RouteStore.add` (route_store.ts:57-64): `addRouteToMap(this.map, routeId, summary.mode, summary.short_name, ...)`. Shape fetch (data/api.ts:147-155):

```ts
export async function fetchRouteShape(routeId: string): Promise<ShapeFeature | null> {
  const url = `/api/routes/${routeId}/shape/`;
  ...
}
```

Paint factory (line 33-60) focus expression:

```ts
'line-opacity': [
  'case',
  ['in', ['get', 'route_id'], ['literal', focused]], 1.0,
  0.2,
],
```

**Bonus — fleet_layer ile karşılaştırma:** `fleet_layer.ts:60-67` aynı `['in', ['get', 'route_id'], ['literal', focused]]` ifadesini vehicle feature'ları üstünde uyguluyor. Recon raporu Bölüm 3'e göre vehicle.route_id backend'de `hat_kodu` (`"29B"`) form'unda yazılıyor; focused array ise PK-formatlı (`["iett:1562", "iett:1564", ...]`) — iki tarafın string format'ı uyuşmadığı için fleet focus bus için silent fail. Polyline tarafında her iki taraf PK-formatlı olduğundan aynı bug oluşmuyor.

---

## Bölüm 5 — Identity conversion helper'ları

**Bulgu:** Frontend codebase'inde route_id ↔ short_name çevrim helper'ı YOK. `routeIdToShortName`, `shortNameOf`, `getRoute(...)` gibi pattern'ler grep'te bulunamadı. Tek translation noktası `RouteStore.getMeta(routeId)` — full RouteSummary döndürür, çağıran `meta.short_name` field'ına direkt erişir. `iett:` literal'i hiçbir production .ts dosyasında hardcoded değil; sadece `api.ts:15`'te yorum olarak ve test fixture'larında geçiyor.

`grep "routeIdToShortName|shortNameOf|getRoute("` → no matches.

`grep "iett:"` production dosyalarında tek match — `frontend/src/data/api.ts:15`:

```ts
export interface RouteSummary {
  id: number;
  route_id: string;          // "public:1298" or "iett:NNNN"
  short_name: string;
```

Geri kalan `iett:` occurrence'larının tümü (~20+) `*.test.ts` fixture'ları içinde (örn. `route_panel.test.ts:26`, `route_panel_flatten.test.ts:30`, `state/snapshot_store.test.ts:43-50`, `render/route_lines_layer.test.ts:47`).

Tek getMeta call site `frontend/src/ui/vehicle_popup.ts:33-34`:

```ts
export function showVehiclePopup(
  ...
  routeStore: RouteStore,
): Popup {
  const meta = props.route_id ? routeStore.getMeta(props.route_id) : null;
```

Vehicle popup için: `props.route_id` değeri canlı vehicle feature'ından geliyor (fleet_layer'ın setData çıktısı), yani bus için `"29B"` formatında. RouteStore key'leri ise `"iett:1562"` formatında (Bölüm 1). `getMeta("29B")` → `null` döner; popup line 80-91 (`renderIettPopup`) `if (!meta)` branch'ına düşer ve "Bu araç henüz hat eşlemesi yapılmamış" mesajını gösterir — recon raporu Bölüm 3'teki silent-fail davranışı bu satırda materyalize oluyor.

`Route` interface'i tek bir objede `route_id` (PK-formatlı) ve `short_name`'i birlikte tutuyor (api.ts:13-24); bir lookup elimizde varsa diğer field'a erişim getter çağrısı tek satır.
