# KM3-a Direction Bug — Teşhis Raporu

**Tarih:** 2026-05-01
**Bağlam:** KM3-a smoke'ta tüm scheduled metro araçları tek yönde
hareket ediyor görüldü. Kod değiştirilmeden önce hangi katmanda
bug'ın olduğunu lokalize etmek için yapılan veri analizi.
**Karar:** Fix bir sonraki mesajda; bu mesajda yalnız teşhis raporu
+ `window.__sf` debug expose commit ediliyor (KM3-b'de temizlenecek).

---

## 1. Backend — M2 direction semantiği

`Route.objects.filter(short_name='M2', route_id__startswith='public:')`:

```
M2 route: route_id='public:1298'  long_name='YENİKAPI - HACIOSMAN'

direction_id=0: trip_id=3104360 headsign='HACIOSMAN'
  ilk durak (seq=1) : 'Yenikapı'      lat=41.0056 lon=28.9514
  son durak (seq=15): 'Hacıosman'     lat=41.1398 lon=29.0305
  shape_id          : 716  shape.shape_id='2476'

direction_id=1: trip_id=3104454 headsign='YENİKAPI'
  ilk durak (seq=1) : 'Hacıosman'     lat=41.1398 lon=29.0305
  son durak (seq=14): 'Yenikapı'      lat=41.0056 lon=28.9514
  shape_id          : 717  shape.shape_id='2477'
```

→ **Bulgu:** Her yön **AYRI shape** kullanıyor. dir=0 → `'2476'`,
dir=1 → `'2477'`. Tek-shape varsayımı geçersiz.

(Adım 1'de "direction_id=0 Yenikapı'dan başlıyor" sorusunun cevabı:
Evet — Yenikapı→Hacıosman.)

---

## 2. Backend — Shape doğal yönü

```
shape_id=2476 (vertex sayısı: 121)
  ilk vertex (coords[0])  : lon=28.9514 lat=41.0056   ← Yenikapı
  son vertex (coords[-1]) : lon=29.0305 lat=41.1398   ← Hacıosman

shape_id=2477 (vertex sayısı: 121)
  ilk vertex (coords[0])  : lon=29.0305 lat=41.1398   ← Hacıosman
  son vertex (coords[-1]) : lon=28.9514 lat=41.0056   ← Yenikapı
```

→ **Bulgu:** Her shape kendi yönünde ham geliyor. `'2476'` =
Yenikapı→Hacıosman, `'2477'` = Hacıosman→Yenikapı. **Backend hiçbir
reverse beklemiyor**; trip'i shape'iyle eşleştirmek yeterli.

(Adım 2'nin sorusu "shape coords[0] Yenikapı'da mı Hacıosman'da mı":
**Hangi shape olduğuna bağlı** — `'2476'` Yenikapı'da, `'2477'`
Hacıosman'da.)

---

## 3. Frontend kodu — `simulation/scheduled_trip.ts:38-42`

```ts
// direction_id=1 → reverse the shape so the trip walks start → end on the
// working polyline. Reverse copy (`[...shape].reverse()`) keeps the cached
// forward shape in route_lines_layer untouched.
const polyline: LonLat[] =
  trip.direction_id === 1 ? [...shape].reverse() : [...shape];
```

→ **Bulgu:** Kod `direction_id === 1` ise reverse uyguluyor.
Varsayım: `shape` parametresi **direction_id=0 yönlü doğal shape**
ve dir=1 trip'i için manuel ters çevrilmesi gerek. Bu varsayım §1-2
ile çelişiyor — backend her yön için **kendi yönlü** shape veriyor.

---

## 4. Cache durumu — `route_lines_layer` ne içeriyor?

`/api/routes/public:1298/shape/` çağrısı:

```
shape_id            : 2477
first vertex        : [29.0305, 41.1398]    ← Hacıosman
last  vertex        : [28.9514, 41.0056]    ← Yenikapı
```

→ **Bulgu:** RouteStore.add() endpoint'i `'2477'` döndürüyor (yani
**dir=1 yönlü shape**). KM3'te yüklenen 21 always-visible polyline
arasında M2 için cache'lenen tek shape budur.

Backend view (`apps/gtfs/views.py:96-99`) `Trip.objects.filter(...)
.first()` ile sırasız ilk trip'i alıyor — bu trip dir=1 olduğunda
(burada öyle olmuş) shape `'2477'` döner. Sıra deterministik değil;
başka route'larda farklı olabilir.

Şu anki M2 aktif trip dağılımı (`/api/trips/active/?mode=metro`):

| direction_id | trip count | shape_id |
|---:|---:|---|
| 0 | 8 | `'2476'` |
| 1 | 7 | `'2477'` |

`getShapeFor` cache'inde sadece `'2477'` var. Sonuç:

| Trip yönü | Trip shape_id | Cache hit? | prepareTrip sonucu |
|---|---|---|---|
| dir=0 | `'2476'` | ❌ miss | `null` (skipNoShape++) — **görünmüyor** |
| dir=1 | `'2477'` | ✅ hit | reverse uygulanır → polyline Yenikapı→Hacıosman → **dir=0 gibi animate** |

(`window.__sf._debugEntries()` browser console'unda doğrulanabilir;
expose bu commit'te eklendi. Bu raporda backend kanıtı yeterli kabul
edildi — gözlemci kullanıcıdan F12 isteğe bağlı.)

---

## Teşhis — Olasılık D (A/B/C kapsamı dışı, iki katmanlı bug)

Kullanıcının A/B/C şıklarından hiçbiri tam değil. Bug **iki yerde
birden**:

1. **`route_lines_layer` per-route TEK shape cache'liyor.** Backend
   `/api/routes/{id}/shape/` view'ı sırasız ilk trip'in shape'ini
   döner — bazı route'larda dir=0 shape, bazılarında dir=1 shape.
   M2'de cache `'2477'` (dir=1) → dir=0 trip'leri shape miss →
   `skippedNoShape++` → ekrandan kayboluyor.

2. **`prepareTrip` `direction_id===1` için reverse uyguluyor.**
   Backend her yön için kendi yönlü shape sağlıyor (M2 dir=0 →
   `'2476'`, dir=1 → `'2477'`). Reverse fazladan — eğer dir=1 trip
   doğru shape'ini bulursa (KM3-a'da bulamıyor ama bulsa), reverse
   onu dir=0 yönüne çevirir. Yani **bug-1 düzeltilince bug-2 ortaya
   çıkar**.

Görsel sonuç: dir=0 trip'leri (8 adet) tamamen ekrandan eksik;
dir=1 trip'leri (7 adet) reverse uygulanıp Yenikapı→Hacıosman gibi
animate ediliyor → kullanıcının "tek yön" gözlemi.

---

## Önerilen düzeltme yönü (KM3-b başlangıcı, bu mesajda kod yok)

İki seçenek:

- **(i) Lazy shape fetch by shape_id.** Backend'e
  `GET /api/shapes/{shape_id}/` endpoint ekle (mevcut
  `ShapeGeoJSONSerializer`'ı yeniden kullan). Frontend `prepareTrip`
  öncesi `trip.shape_id` ile lazy fetch + `shapeIndex` cache.
  `direction_id===1` reverse mantığını kaldır.
- **(ii) Eager: route'un tüm shape'lerini yükle.** Backend
  `RouteViewSet.shape` action'ını liste döndürecek şekilde değiştir
  (veya yeni `shapes` action) → RouteStore.add() bunları topluca
  cache'lesin. Reverse mantığını kaldır.

KM3-b'nin mode genişlemesinde shape varyantı zaten sorun çıkaracak
(her route 1-3 shape paylaşır) — (i) lazy daha ölçeklenebilir, fetch
ihtiyacı uyumlu artar. (ii) eager peşin yükleme bedeline daha net
state sağlar.

---

## Bu commit'in sınırı

- Bu rapor (`docs/phase5_km3a_direction_bug.md`)
- `window.__sf = scheduledFleet` debug global (`main.ts`)
- `ScheduledFleet._debugEntries()` getter — KM3-b'de **silinecek**

Fix uygulanmadı. Bir sonraki mesajda (i) veya (ii) seçimi sonrası
KM3-b kapsamında çözülecek.
