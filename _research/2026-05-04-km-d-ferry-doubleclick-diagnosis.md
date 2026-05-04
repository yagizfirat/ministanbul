# KM-d Tanı: Vapur (Şehir Hatları A.Ş.) çift tıklama sessiz

**Tarih:** 2026-05-04
**İlgili borç:** Spec Ek A.19 #6 (yayın blokeleyici)
**Smoke kaynağı:** Yağız 2026-05-04 manuel browser smoke
**Kapsam:** Sadece kod okuma, hipotez analizi. Commit yok.

---

## Özet bulgu

Vapur hatlarına panel'de çift tıklayınca focus + bbox + zoom hiçbir şey
yapmıyor görünüyor. Console'da log/error/toast yok (Yağız raporu).

**Kod okuması, en muhtemel kök nedeni HİPOTEZ (c) olarak işaret ediyor:**
ferry hatları map'in route-lines layer'ına **hiç eklenmiyor**. `addRouteToMap`
çağrılmadığı için `getRoutesBBox(routeIds)` ferry için her zaman `null`.
Fallback `SnapshotStore.getVehicleBBoxForRoutes` İETT canlı araçlara bakar,
vapur scheduled (tarife-bazlı) olduğundan o da `null`. Sonuç: bbox=null →
`showToast('Bu hatta şu an aktif araç yok, zoom yapılamadı')` çağrısı yapılır
→ kullanıcı "sessizlik" hisseder (toast var ama zoom yok ya da toast UI'da
gözükmüyor).

---

## Kod yolu izlemesi

### 1. Panel tarafı — handler attach var mı? (hipotez (b) cevabı)

`frontend/src/ui/route_panel.ts`:

- **Single satır** (`renderRouteItem`, line 398-447): `dblclick` handler line
  440-445 `opts.onRouteDoubleClick?.(route.route_id)` çağırır. Mod-bağımsız.
- **Variant header** (`renderVariantHeader`, line 348-396): `dblclick` handler
  line 391-394 `opts.onVariantGroupDoubleClick?.(ids)` çağırır. Mod-bağımsız.
- **Variant satırı** (`renderVariantItem`, line 321-346): `dblclick` handler
  line 341-344. Mod-bağımsız.

`flattenRoutesForDisplay` (`route_panel_flatten.ts`) ferry route'larını mode
field'ına göre `MODE_ORDER` içindeki `ferry` grubuna yerleştirir. Tek-variant
ferry → `single`, çoklu-variant ferry → `group-header` + `group-variant`.

> **Hipotez (b) — düşer.** Variant grup header dblclick handler ferry için
> de wire edilmiş. Tüm üç render path (single / variant-header / variant) aynı
> `dblclick` listener'ını alır. Mod özel ayrım yok.

### 2. Callback tarafı — `focusAndZoom` ne yapar?

`frontend/src/main.ts:217-244`:

```ts
routePanel = createRoutePanel({
  ...
  onRouteDoubleClick: (routeId) => focusAndZoom([routeId]),       // line 221
  onVariantGroupDoubleClick: (routeIds) => focusAndZoom(routeIds), // line 222
});

function focusAndZoom(routeIds: readonly string[]): void {
  routeFocus.setFocus(routeIds);                                   // line 234
  const bbox = getRoutesBBox(routeIds)                             // line 238
    ?? store.getVehicleBBoxForRoutes(routeIds);
  if (bbox) {
    map.fitBounds(bbox as [number, number, number, number], { padding: 80 });
  } else {
    showToast('Bu hatta şu an aktif araç yok, zoom yapılamadı');
  }
}
```

İki bbox kaynağı denenir, sonra fallback toast.

### 3. `getRoutesBBox` ne tarar?

`frontend/src/render/route_lines_layer.ts:189-210`:

```ts
export function getRoutesBBox(routeIds): [number, number, number, number] | null {
  ...
  for (const f of collection.features) {
    if (!idSet.has(f.properties.route_id)) continue;
    ...
  }
  return found ? [...] : null;
}
```

`collection.features` tarar. Bu collection'a feature ekleyen tek yer
`addRouteToMap` (line 153-166):

```ts
export function addRouteToMap(map, routeId, mode, shortName, color, shape): void {
  ...
  collection.features.push(feature);
  shapeIndex.set(...);
  flush(map);
}
```

`addRouteToMap`'i çağıran tek yer `RouteStore.add()` (`state/route_store.ts:46-68`):
shape backend'den çekilip MapLibre source'a push edilir.

### 4. **Kritik:** `RouteStore.add` ferry için çağrılıyor mu?

`frontend/src/main.ts:152-198` (loadAlwaysVisibleRoutes):

```ts
async function loadAlwaysVisibleRoutes(): Promise<void> {
  let polylineSummaries = await fetchActiveRoutes(ALWAYS_VISIBLE_MODES);
  routeStore.registerSummaries(polylineSummaries);
  ...
  for (let i = 0; i < polylineSummaries.length; i += ROUTE_FETCH_BATCH) {
    const batch = polylineSummaries.slice(i, i + ROUTE_FETCH_BATCH);
    const results = await Promise.allSettled(
      batch.map(async (s) => ({ s, outcome: await routeStore.add(s.route_id) })),
    );
    ...
  }
  ...
  // KM1 alt-iş f-6 — RoutePanel + route filter wiring.
  // Ferry polyline çizilmez (KM3 paterni) ama panel'de listelenir;
  // scheduled vehicle layer'ı route_id filter'ına tabi olduğu için
  // ferry default visible kalır (vapur scheduled noktalar görünür).
  let ferrySummaries: RouteSummary[] = [];
  try {
    ferrySummaries = await fetchActiveRoutes(['ferry']);
    console.log(`[routes] ferry metadata for panel: ${ferrySummaries.length}`);
  } catch (err) { ... }

  const initialRoutes = [...polylineSummaries, ...ferrySummaries];
  ...
}
```

**Kanıt:** Ferry için sadece `fetchActiveRoutes(['ferry'])` çağrılıp
`ferrySummaries` panel'e besleniyor. **`routeStore.add(s.route_id)` ferry
için ÇAĞRILMIYOR.** Bilinçli karar (line 190-191 yorumu): ferry polyline
çizilmiyor (KM3 paterni: vapur denizüstü düz çizgi anlamsız, scheduled
nokta zaten yeterli görsel).

Sonuç: `collection.features` ferry route_id'lerini İÇERMİYOR. Dolayısıyla
`getRoutesBBox(['ferry:bostanci-kadikoy'])` → `null`.

### 5. Fallback: `SnapshotStore.getVehicleBBoxForRoutes`

`frontend/src/state/snapshot_store.ts:99-124`:

```ts
getVehicleBBoxForRoutes(routeIds): [...] | null {
  ...
  for (const v of this.t1.vehicles.values()) {
    if (v.route_id === null || !idSet.has(v.route_id)) continue;
    ...
  }
  return count === 0 ? null : [...];
}
```

`SnapshotStore` İETT canlı araçların (`vehicles_all_update` WS payload)
snapshot'ını tutar. Vapur **scheduled** (tarife-bazlı simülasyon, `ScheduledFleet`
sınıfı), SnapshotStore'da yer almaz. `idSet.has(v.route_id)` ferry route_id'si
için her zaman false → count=0 → return null.

**`ScheduledFleet`** (`simulation/scheduled_fleet.ts:18+`) içinde
`getVehicleBBoxForRoute` veya `getRouteBBox` benzeri **public method YOK**.
Fallback için kullanılabilir hazır helper bulunmuyor.

### 6. Sonuç: bbox=null → showToast çalıştırılır

main.ts:241-243:

```ts
} else {
  showToast('Bu hatta şu an aktif araç yok, zoom yapılamadı');
}
```

**Kod yolu çalışırsa toast görünmeli.** Yağız "toast yok" raporladığına göre
ya (i) toast görünüyor ama Yağız fark etmedi, ya (ii) toast UI'da gerçekten
render olmadı (CSS / DOM mounting / showToast bug). Bunu DevTools breakpoint
ile ayrıştırmak gerekecek.

---

## Üç hipotezin değerlendirmesi

### (a) Şehir Hatları A.Ş. agency_id farklı render path'e düşüyor

**Düşer.** Panel render path tamamen `mode` field'ına bağlı (`MODE_ORDER`,
`flattenRoutesForDisplay`). `agency_id` / `agency_name` panel'de sadece
`renderRouteItem`'in operatorEl'inde (line 430-432) görüntü amaçlı
gösterilir, render path seçimine etki etmez. Ferry mode == 'ferry'
`MODE_ORDER`'da var (line 57: `{ key: 'ferry', label: 'Vapur' }`), dolayısıyla
panel'de görünür ve aynı dblclick handler'larını alır.

**Olasılık:** %5

### (b) Variant grup header dblclick handler sadece bus için wire edilmiş

**Düşer.** `route_panel.ts`'de tüm üç render path (`renderRouteItem`,
`renderVariantHeader`, `renderVariantItem`) için dblclick listener
mod-bağımsız attach edilir (line 341-344, 391-394, 440-445). Bus zaten
v0.8.0'da panel'den çıkarıldı (KM5-e.2: iki toggle satırı, MODE_ORDER
dışında). Yani bus için özel handler hiç olmadı.

**Olasılık:** %2

### (c) `getRouteBBox` ferry için null/empty, vehicle bbox fallback sadece İETT

**EN GÜÇLÜ HİPOTEZ.** Yukarıdaki kod yolu izlemesi bunu kesinlikle
kanıtlıyor:

1. `addRouteToMap` ferry için hiç çağrılmaz (main.ts:192-198 ferry shape
   yüklemiyor) → `getRoutesBBox` ferry için her zaman `null`.
2. `SnapshotStore.getVehicleBBoxForRoutes` İETT canlı vehicle'a bakar,
   vapur scheduled olduğundan ferry için her zaman `null`.
3. `ScheduledFleet`'te bbox helper yok.

Toast yine de çağrılması gerek. Yağız toast'u görmediyse ek bir
sub-hipotez (c.1) var: toast UI render bug. Ama ana kök neden hipotez (c).

**Olasılık:** %90

---

## Browser smoke listesi (Yağız için, yarın akşam)

DevTools açık + Console + Sources tab. M2 metro çift tıklamasını **kontrol
referansı** olarak kullan (zoom çalışmalı). Sonra vapur hattıyla aynı
deneyi yap, farkı not et.

### Smoke 1 — handler attach kontrolü
Sources tab → `route_panel.ts:443` (renderRouteItem dblclick callback,
`opts.onRouteDoubleClick?.(route.route_id)` satırı) **breakpoint koy**.
Vapur (örn. "Beşiktaş - Üsküdar" satırı, panel Vapur grubunda) çift tıkla.
- **Breakpoint hit ederse:** handler attach var, kod buraya kadar geliyor.
  Hipotez (b) zaten düşmüştü, kesinleşir.
- **Breakpoint hit etmezse:** handler attach edilmemiş → flatten farklı
  yola düşürmüş olabilir, kod okumadaki varsayım yanlış. Hipotez (a) tekrar
  yükselir.

### Smoke 2 — focusAndZoom ulaşıyor mu
Smoke 1 hit ederse, `main.ts:233` `focusAndZoom` fonksiyon başına breakpoint
ekle, F8 ile devam. Vapur çift tıkla, `routeIds` değerini incele
(`['ferry:...']` formatında olmalı).

### Smoke 3 — bbox null doğrulama (KRİTİK)
`main.ts:238` `const bbox = getRoutesBBox(routeIds) ?? store.getVehicleBBoxForRoutes(routeIds);`
satırına breakpoint koy. Step over sonrası Console'a yaz:
```js
getRoutesBBox(routeIds)               // beklenen: null
store.getVehicleBBoxForRoutes(routeIds) // beklenen: null
bbox                                   // beklenen: null
```
Üç de null ise hipotez (c) **kesin doğrulanır**. M2 metro ile aynı deney:
`getRoutesBBox` valid bbox dönmeli (M2 polyline collection'da var).

### Smoke 4 — toast UI render kontrolü
`main.ts:242` `showToast(...)` satırına breakpoint koy. Hit ederse
Step Over → DOM'a bak: `document.querySelector('.toast')` veya benzer
toast container görünür mü? Element var mı? Görünür mü
(`getComputedStyle(...).visibility`)?
- **Toast DOM'da var ve görünür → Yağız smoke'da kaçırmış**, kök neden
  hipotez (c) saf hali.
- **Toast DOM'da yok / opacity 0 / display none → ek toast UI bug** (sub-hipotez c.1).

---

## Fix taslakları

Smoke sonuçlarına göre uygulanacak. Her biri 5-15 satır.

### Fix-A — Hipotez (c) ana kök neden, ScheduledFleet bbox helper

`frontend/src/simulation/scheduled_fleet.ts`'e public method ekle:

```ts
// KM-d fix: ferry/scheduled hatlar için bbox fallback. SnapshotStore
// İETT canlı kapsamında, vapur scheduled — ScheduledFleet'in active
// trip polyline'larından union bbox hesaplar.
getRouteBBox(routeId: string): [number, number, number, number] | null {
  let minLon = Infinity, minLat = Infinity;
  let maxLon = -Infinity, maxLat = -Infinity;
  let found = false;
  for (const trip of this.activeTrips.values()) {
    if (trip.route_id !== routeId) continue;
    for (const [lon, lat] of trip.polyline) {
      if (lon < minLon) minLon = lon;
      if (lon > maxLon) maxLon = lon;
      if (lat < minLat) minLat = lat;
      if (lat > maxLat) maxLat = lat;
    }
    found = true;
  }
  return found ? [minLon, minLat, maxLon, maxLat] : null;
}

getRoutesBBox(routeIds: readonly string[]): [number, number, number, number] | null {
  // Union over multiple route_ids (variant group). Tek tek getRouteBBox
  // çağırıp birleştirir.
  // ... (5 satır implementasyon)
}
```

`main.ts:238` üçüncü fallback olarak ekle:

```ts
const ferryFleet = scheduledFleets.get('ferry');
const bbox = getRoutesBBox(routeIds)
  ?? store.getVehicleBBoxForRoutes(routeIds)
  ?? ferryFleet?.getRoutesBBox(routeIds)
  ?? null;
```

Test: `scheduled_fleet.test.ts`'e `getRouteBBox` case (active trip varken
union bbox, route_id eşleşmediğinde null, no active trip null).

### Fix-B — Hipotez (c.1) toast UI render bug (smoke 4'te ortaya çıkarsa)

`frontend/src/ui/toast.ts` (varsa) içeriği oku, mount/visibility/CSS
bul. Olası kök:
- Container DOM'a append edilmemiş (init eksik)
- z-index çok düşük, MapLibre canvas üstüne binmiyor
- Animation timer 0 → fadein/fadeout aynı tick'te tetikleniyor
- `document.body.appendChild` yerine eski `routePanel.element` üstüne
  takılı, panel `display:none` ise toast da görünmez

Patch boyutu kök sebebe göre 3-15 satır.

### Fix-C — Hipotez (a) ferry mode-ayrımı (düşük olasılık)

Smoke 1 breakpoint hit etmezse aktif olur. `flattenRoutesForDisplay` ferry
için yanlış kind döndürüyor mu, `mode === 'ferry'` filter'ı bozuk mu
incelenir. Yamak büyüklüğü `route_panel_flatten.ts`'in yeniden okunmasıyla
netleşir.

---

## Kapanış

- Yarın akşam Smoke 1-4 sırayla → kök neden 5 dk içinde net olur.
- Hipotez (c) %90 — Fix-A 1-2 saatlik iş + 2-3 vitest case.
- Smoke 4 toast bug'ı ortaya çıkarsa Fix-B ek 30-60 dk.

ROADMAP'e dokunulmadı. Commit yok.
