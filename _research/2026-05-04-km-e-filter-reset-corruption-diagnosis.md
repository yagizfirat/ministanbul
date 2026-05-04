# KM-e Tanı: Filter Reset state corruption (yayın blokeleyici)

**Tarih:** 2026-05-04
**İlgili borç:** Spec Ek A.19 #7 (yayın blokeleyici, kritik)
**Smoke kaynağı:** Yağız 2026-05-04 manuel browser smoke
**Kapsam:** Sadece kod okuma + hipotez analizi. Commit yok.
**Kritik not:** Kod okuması donma'nın kök nedenini KESIN olarak ortaya
çıkarmıyor — runtime profiling (Performance + Memory tab) olmadan
hipotezler sıralamada kalır. Yarın akşam smoke kritik.

---

## Özet bulgu

Reset / "Tümü" / hat checkbox'ları toplu açma sonrası frontend donuyor,
F5'e kadar düzelmiyor. Kod okuması iki **bilinmeyen** ortaya çıkardı:

1. **Filter çakışması (kesin bug, donma sebebi olabilir veya olmayabilir)**:
   `fleet-circles` layer'ına iki ayrı filter sistemi setFilter ediyor —
   `applyFleetVisibilityFilter` (is_metrobus-based, KM5-e.2) ve `applyFilters`
   (route_id-based, KM1 f). Sonuncusu kazanır, mantıksal tutarsızlık var.

2. **MapLibre setFilter chain maliyeti (hipotez)**: Reset 1 fire = 3 ardışık
   setFilter (route-lines, scheduled-circles, fleet-circles). Render loop
   her frame'de `updateFleet` + `updateScheduled` setData çağırıyor (~6900
   araç). setFilter + setData çakışmasının paint pipeline'ı boğması mümkün
   ama kanıtlanmadı.

**Kod okuması, listener accumulation veya snapshot reducer kilitlenmesi
için kanıt göstermiyor.** Hipotez (b) ve (c) düşük olasılık.

---

## Reset akış zinciri

### 1. Button click → state mutation

`frontend/src/ui/route_panel.ts:163-166`:

```ts
const resetBtn = document.createElement('button');
resetBtn.textContent = 'Reset';
resetBtn.addEventListener('click', () => onReset());

function onReset(): void {
  opts.visibility.resetToDefault(opts.defaultVisibleIds);
}
```

Tek click → tek `resetToDefault` çağrısı.

### 2. RouteVisibility — fire 1 KEZ

`frontend/src/state/route_visibility.ts:79-93`:

```ts
resetToDefault(defaultIds: readonly string[]): void {
  if (defaultIds.length === this.visible.size) {
    let allMatch = true;
    for (const id of defaultIds) {
      if (!this.visible.has(id)) { allMatch = false; break; }
    }
    if (allMatch) return;  // no-op guard
  }
  this.visible.clear();
  for (const id of defaultIds) this.visible.add(id);
  this.fire();  // tek fire
}

private fire(): void {
  const snapshot: ReadonlySet<string> = new Set(this.visible);
  for (const fn of this.listeners) fn(snapshot);
}
```

`resetToDefault` net: 1 fire. Listener iki tane (aşağıda). No-op guard var
(zaten default state'te ise return).

### 3. İki listener tetiklenir

`main.ts:301`: `routeVisibility.subscribe(applyFilters)`
`route_panel.ts:234-236`: `opts.visibility.subscribe(() => syncCheckboxes())`

**`applyFilters`** (main.ts:288-300):
```ts
function applyFilters(): void {
  if (!routeVisibility) return;
  const routeF = getRouteFilter(routeVisibility.getVisible(), routeVisibility.getTotalCount());
  if (map.getLayer('route-lines')) {
    map.setFilter('route-lines', routeF as never);
  }
  if (map.getLayer('scheduled-circles')) {
    map.setFilter('scheduled-circles', routeF as never);
  }
  if (map.getLayer('fleet-circles')) {
    map.setFilter('fleet-circles', routeF as never);
  }
}
```

**3 ardışık setFilter** — aynı `routeF` expression, üç layer.

**`syncCheckboxes`** (`route_panel.ts:479-504`): DOM'daki checkbox'ları
RouteVisibility state'ine göre günceller. Iterates over `groupsByMode`
itemByKey Map'i (~120 entry polyline+ferry için). DOM read/write, hızlı.

### 4. Filter expression — boyut analizi

`getFilterExpression` (`route_visibility.ts:111-118`):

```ts
if (visible.size === 0) return FILTER_NEVER;          // ['==', ['get', 'route_id'], '__none__']
if (visible.size === totalCount) return null;         // setFilter null = clear
return ['in', ['get', 'route_id'], ['literal', Array.from(visible)]];
```

- **Reset / Tümü** → `visible.size === totalCount` (defaultIds == initialIds == ALL_ROUTES) → `null` filter (clear)
- **Hiçbiri** → `visible.size === 0` → `FILTER_NEVER`
- **Manuel checkbox flip** → `['in', 'route_id', [...]]` literal listesi

Total polyline + ferry = ~120 route_id (bus iptal, KM5-e.2). Filter
expression literal max ~120 entries — MapLibre style spec için makul.

### 5. fleet-circles çakışması (KESIN BUG)

**KRİTİK BULGU**: `fleet-circles` layer'ına **iki ayrı sistem** setFilter
ediyor:

**Sistem A** — `applyFleetVisibilityFilter` (main.ts:210-216):
```ts
function applyFleetVisibilityFilter(): void {
  if (!map.getLayer('fleet-circles')) return;
  map.setFilter(
    'fleet-circles',
    buildFleetFilter(busVisible, metrobusVisible) as never,
  );
}
```
`buildFleetFilter` (`fleet_layer.ts:91-100`):
```ts
return [
  'case',
  ['==', ['get', 'is_metrobus'], true], metrobusVisible,
  busVisible,
];
```

**Sistem B** — `applyFilters` (main.ts:288-300, yukarıda):
```ts
map.setFilter('fleet-circles', routeF as never);  // route_id-based
```

İki sistem **aynı layer'a setFilter eder, sonuncusu kazanır**:

- Sayfa açılır → `applyFilters()` (line 302) → fleet-circles route_id-based
- Kullanıcı bus toggle kapatır → `applyFleetVisibilityFilter()` → fleet-circles is_metrobus-based. **Önceki route_id filter EZİLDİ**.
- Kullanıcı Reset basar → `applyFilters()` → fleet-circles route_id-based. **is_metrobus filter EZİLDİ**.

**Yan etki:** İETT canlı vehicle'larında (KM5-a sonrası) `route_id`
çoğunlukla `null` (mapping retire). `['in', ['get', 'route_id'], ['literal', [...]]]`
expression `null` değer için `false` döner → **Reset sonrası tüm İETT
araçları fleet-circles'tan gizlenir**. Bus + metrobüs noktalar görsel
olarak kaybolur.

Bu donma sebebi olmayabilir ama **kullanıcı UX bozucu yan etki**: Yağız
"Reset bastım, araçlar kayboldu, tıklamalarım çalışmıyor sandım, F5 attım"
yaşamış olabilir.

### 6. Render loop — her frame setData

`startRenderLoop` (main.ts:311-325):

```ts
function frame(): void {
  const positions = store.getInterpolated(performance.now());
  updateFleet(map, positions);                    // setData fleet-circles
  ...
  updateScheduled(map, allScheduled);              // setData scheduled-circles
  requestAnimationFrame(frame);
}
```

Her frame'de iki setData çağrısı (`updateFleet` line 112-128, source.setData
ile yeni FeatureCollection). 6900 İETT canlı + 1500-2000 scheduled = ~8500
feature/frame.

setFilter + setData aynı layer'a aynı tick'te çakışırsa MapLibre paint
pipeline yeniden yığın hesaplaması yapar. Tile-bazlı filter eval ek maliyet.
Ama bu sayfa açıldığından beri çalışıyor — F5 sonrası "düzelmesi" için
Reset-sonrası bir state olmalı.

### 7. Listener accumulation — kod okumasıyla yok

- `routeVisibility.subscribe` × 2 (main.ts:301, route_panel.ts:234) — module
  init'te bir kez. Panel destroy/recreate yapılmıyor.
- DOM event listener'ları `applySearch` / `rebuildItems` her çağrıda yeni
  DOM'a yeni listener attach. Eski DOM `replaceChildren()` ile referansı
  kopar → GC alır. Listener ile birlikte. JS short-lived, sızıntı yok.

Statik kanıt accumulate eden bir şey göstermiyor. Ama runtime'da
`document.body` veya `map.on(...)` üzerine takılan listener varsa
görülmüyor olabilir.

---

## Üç hipotezin değerlendirmesi

### (a) MapLibre setFilter × N ardışık çağrı, style spec invalidation döngüsü

**ORTA OLASILIK**. Reset 1 fire = 3 setFilter. Manuel checkbox toplu açma
5-10 click → 5-10 fire = 15-30 setFilter ardışık. Render loop her 16 ms'de
2 setData çağırıyor. setFilter ve setData aynı layer'a çakıştığında
MapLibre internal paint queue'da iş birikebilir.

KM-a fix'i (commit `5b5007e`) zaten benzer bir patolojiyi
(`setPaintProperty` `case → interpolate(zoom)` ihlali) açığa çıkardı —
MapLibre 5.x style spec edge case'lerine duyarlı. Setfilter cumulative
maliyet senaryosu mümkün.

Ama tek başına Reset (3 setFilter) donma için yetmemeli — render loop'un
süreklilik yarattığı koşul gerek.

**Olasılık:** %45

### (b) Memory leak — listener accumulation

**DÜŞÜK OLASILIK**. Kod okuması accumulate gösteriyor değil. Panel
destroy/recreate yapılmıyor, subscribe'lar tek seferlik. DOM listener'ları
`replaceChildren` ile kopar → GC alır. **Statik kanıt yok**.

Ama runtime'da `map.on('click', ...)` veya `document.addEventListener` her
filter değişiminde tekrar ekleniyor olabilir — kod okumasıyla görülmedi
ama kanıt olmadan reddedilemez. Memory tab heap snapshot kesin sonuç verir.

**Olasılık:** %15

### (c) Snapshot diff reducer kilitleniyor

**DÜŞÜK OLASILIK**. Reset visibility filter'ı; SnapshotStore (İETT canlı
snapshot reducer) ile direct bağlantı yok. WS payload reducer her tick'te
çalışır (60s polling), filter değişimine reaktif değil.

Tek kanıtlı bağlantı: Reset sonrası `route_id`-based filter İETT araçlarını
gizler (yukarıdaki çakışma bulgusu). Bu reducer kilidi değil, **filter
mantığı yanlışlığı**.

**Olasılık:** %10

### (d) ek hipotez — fleet-circles filter çakışması + render loop interaction

**ORTA OLASILIK** (kod okuması bunu açığa çıkardı). Yukarıda 5. madde
detaylı: Reset → fleet-circles filter `applyFleetVisibilityFilter` filter'ını
ezer → İETT araçları kaybolur (route_id null). Render loop her frame
setData çağırıyor → 6900 araç features yeniden yüklenir ama hepsi
filter'lı (görünmez).

Donma için ek bir tetikleyici lazım: belki MapLibre filter null + setData
6900 feature kombinasyonu CPU-bound. Veya tile-bazlı filter eval bir
edge case'e takılıyor (örn. `route_id` field'ı eksikse `['get', ...]`
undefined davranışı).

**Olasılık:** %30 (donmaya katkı ihtimali). Ama bu KESIN UX bug, donma
olmasa bile düzeltilmeli.

---

## Browser smoke listesi (Yağız için, yarın akşam)

DevTools açık → Performance + Memory + Console tab. **Sayfa açıldıktan
sonra 30 saniye bekle** (scheduled fleet polling tamamlansın, ~1500
trip yüklensin). Sonra:

### Smoke 1 — Performance Record (KRİTİK)
Performance tab → Record başlat → Reset bas → 5 saniye bekle → Stop.

**Bakılacak:**
- **Long Tasks** (>50ms) frame timeline'ında kırmızı bar var mı?
- Frames timeline'da donma penceresi (FPS 0) var mı, kaç saniye sürüyor?
- Bottom-up'da `setFilter`, `setData`, `paint`, `processStyle` gibi
  fonksiyonların self time'ı.
- GPU column'da paint süresi.

**Beklenen:** Hipotez (a) doğruysa setFilter / processStyle dominant. Hipotez
(d) doğruysa setData her frame yığılıyor.

### Smoke 2 — Memory Heap snapshot karşılaştırma
Memory tab → Heap snapshot → "Snap-A" alın → Reset bas → 5 sn bekle →
"Snap-B" alın. Snap-B → Comparison view → Filter: All objects.

**Bakılacak:**
- Detached DOM elements büyüyor mu (>0)?
- EventListener count büyüyor mu?
- `Map`, `Set`, `Array` object count fark ediyor mu?

**Beklenen:** Hipotez (b) doğruysa listener / detached DOM count büyür.
Yoksa hipotez (b) düşer.

### Smoke 3 — Filter expression doğrulama
Console'da Reset basmadan önce yaz:
```js
JSON.stringify(map.getStyle().layers.find(l => l.id === 'fleet-circles').filter)
JSON.stringify(map.getStyle().layers.find(l => l.id === 'scheduled-circles').filter)
JSON.stringify(map.getStyle().layers.find(l => l.id === 'route-lines').filter)
```
Reset bas, üç çıktıyı tekrar al, **karşılaştır**.

**Beklenen:** fleet-circles filter Reset sonrası `['in', 'route_id', [...]]`
formatına dönüşür → hipotez (d) kesin doğrulanır (is_metrobus-based filter
ezilir).

### Smoke 4 — fleet source feature count
Console:
```js
map.getSource('fleet').serialize().data.features.length          // İETT canlı
map.getSource('scheduled').serialize().data.features.length       // Scheduled
```
Reset öncesi/sonrası rakamları karşılaştır. setData her frame'de yenilendiği
için sürekli değişebilir, **mertebe anlamlı (binler? yüzler?)**.

### Smoke 5 — Manuel multi-click + Performance
Performance Record başlat → 5 farklı raylı hat checkbox'ı (M2, F1, T1, T4,
M7 gibi) hızlı sırayla aç-kapa-aç-kapa → Stop. Donma penceresi var mı?
Eşik: 5 click bile dondurursa hipotez (a) güçlenir.

---

## Fix taslakları

Smoke sonuçlarına göre seçilecek. Tüm fix'ler ek vitest case ile birlikte.

### Fix-A — Hipotez (a) için debounce setFilter

`main.ts`'de `applyFilters`'ı `requestAnimationFrame` ile debounce et.
Tek frame'de birden çok fire() gelirse son state ile tek setFilter:

```ts
let pendingFilterUpdate: number | null = null;
function applyFilters(): void {
  if (pendingFilterUpdate !== null) cancelAnimationFrame(pendingFilterUpdate);
  pendingFilterUpdate = requestAnimationFrame(() => {
    pendingFilterUpdate = null;
    if (!routeVisibility) return;
    const routeF = getRouteFilter(routeVisibility.getVisible(), routeVisibility.getTotalCount());
    if (map.getLayer('route-lines')) map.setFilter('route-lines', routeF as never);
    if (map.getLayer('scheduled-circles')) map.setFilter('scheduled-circles', routeF as never);
    if (map.getLayer('fleet-circles')) map.setFilter('fleet-circles', routeF as never);
  });
}
```

5-10 manuel click → 1 frame'lik debounce → tek setFilter set'i. Donma
hafifler.

**Boyut:** ~10 satır.

### Fix-B — Hipotez (d) için filter çakışması düzeltme

`fleet-circles` layer'ına TEK bileşik filter koy. `applyFilters` ve
`applyFleetVisibilityFilter` aynı yerden bileşik expression üretsin:

```ts
function applyFleetCircles(): void {
  if (!map.getLayer('fleet-circles')) return;
  const routeF = getRouteFilter(routeVisibility.getVisible(), routeVisibility.getTotalCount());
  const visF = buildFleetFilter(busVisible, metrobusVisible);
  // Bileşik: AND. routeF null ise sadece visF, FILTER_NEVER ise hiçbiri.
  let composite: unknown;
  if (routeF === null) composite = visF;
  else if (Array.isArray(routeF) && routeF[0] === '==' && routeF[2] === '__none__') {
    composite = false;
  } else {
    composite = ['all', routeF, visF];
  }
  map.setFilter('fleet-circles', composite as never);
}
```

`applyFilters` ve `applyFleetVisibilityFilter` ikisi de bu helper'ı çağırır.
**Yan etki:** İETT canlı vehicle.route_id null sorunu hala var — `routeF`
İETT araçlarını filtrelemeye yardımcı olmaz. Fix-B sadece çakışmayı
çözer; route_id-null vehicle'ları görmek için `routeF` her zaman null
(tüm geçer) → fleet-circles bus/metrobus toggle'a göre çalışır. Tutarlılık.

Aslında daha temiz: fleet-circles'a ASLA route_id filter uygulama
(mapping kapalı, hat-bazlı filter İETT canlı için anlamsız). `applyFilters`
sadece `route-lines` ve `scheduled-circles`'a setFilter etsin.
`applyFleetVisibilityFilter` tek kanal fleet-circles için.

```ts
function applyFilters(): void {
  if (!routeVisibility) return;
  const routeF = getRouteFilter(routeVisibility.getVisible(), routeVisibility.getTotalCount());
  if (map.getLayer('route-lines')) map.setFilter('route-lines', routeF as never);
  if (map.getLayer('scheduled-circles')) map.setFilter('scheduled-circles', routeF as never);
  // fleet-circles ARTIK BURAYA dokunmuyor — applyFleetVisibilityFilter tek kanal.
}
```

**Boyut:** 1 satır silme + comment, ~5 satır.

### Fix-C — Hipotez (b) için listener leak (smoke 2 doğrularsa)

Heap snapshot detached DOM / listener growth gösterirse:
- `route_panel.ts`'de `subscribe`'a karşılık `unsubscribe` API ekle.
- Panel `destroy()` cleanup eden listener tutma (`subscriptionId` döndür).
- DOM event listener'ları `AbortController` ile iliştir, `destroy` `controller.abort()` çağırır.

**Boyut:** ~15-25 satır (RouteVisibility unsubscribe + panel cleanup).

---

## Tavsiye edilen yarın akşam akış

1. Smoke 1 (Performance Record) → kanıt oluşur, ana hipotez netleşir.
2. Smoke 3 (filter expression diff) → çakışma kesin doğrulanır.
3. Smoke 2 (Memory snapshot) → leak/no-leak ayrımı.
4. Bulguya göre Fix-A + Fix-B kombo (ikisi bağımsız, ikisini birden
   uygulamak mantıklı). Süre ~2-3 saat.

ROADMAP'e dokunulmadı. Commit yok.
