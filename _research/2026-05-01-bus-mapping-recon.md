# Bus Realtime Mapping Pipeline — Keşif (read-only)

**Tarih:** 2026-05-01
**Yöntem:** Salt okuma; pytest/celery/manage.py/redis çalıştırılmadı.
**Kapsam:** backend/apps/realtime/ + frontend mapping-aware kod + spec §5.4 + ROADMAP 5h/5i/5i-v/6h-ii + _research/.

---

## 1. Backend mapping pipeline durumu

**Bulgu:** Pipeline kabuğu mevcut ve aktif (Celery beat 60s fetch + günlük 04:00 mapping refresh). 17 test dosyası `backend/apps/realtime/tests/`'te. Mapping data (`KapiNo → hat_kodu`) `enrich.py`'da Redis'ten okunup vehicle'a `route_id` olarak yazılıyor — ama "hat_kodu" String (örn. `"29B"`), GTFS `Route.route_id` (örn. `"iett:1562"`) ile aynı değil (Bölüm 3'te delillendirilen kritik uyumsuzluk).

| Dosya | Son commit (hash + tarih) | Public API |
|---|---|---|
| `apps/realtime/adapters/__init__.py` | `3fca3af` 2026-04-23 | re-export |
| `apps/realtime/adapters/base.py` | (init ile aynı) | `class BaseAdapter(ABC)` (line 22) |
| `apps/realtime/adapters/iett_soap.py` | (init ile aynı) | `class IettSoapAdapter(BaseAdapter)` (line 265), `_parse_arsiv_response`, `_parse_fleet_response`, `class IettRateLimitViolation` |
| `apps/realtime/admin_views.py` | `7654d0b` 2026-04-26 | `def live_vehicles_view(request)` (line 48) |
| `apps/realtime/calendar.py` | `32dfbb1` 2026-04-25 | `get_day_type`, `pick_target_date(today)`, `_naive_day_type`, `_next_day_type_of`, `_last_sunday_before` |
| `apps/realtime/consumers.py` | `fbfad28` 2026-04-26 | `class EchoConsumer`, `class VehicleAllConsumer` (lines 20, 31) |
| `apps/realtime/enrich.py` | `cd94110` 2026-04-25 | `def enrich_with_route_id(vehicles, mapping) -> list[VehiclePosition]` (line 37) |
| `apps/realtime/mapping.py` | `cd94110` 2026-04-25 | `def build_mapping(records, snapshot_date, snapshot_day_type) -> dict` (line 36); helper `_seconds_of_day` |
| `apps/realtime/schemas.py` | `1a88ed1` 2026-04-23 | `class VehiclePosition(BaseModel)` (line 55), `class IettArsivGorev(BaseModel)` (line 72), `parse_msdate` |
| `apps/realtime/spatial.py` | `c04d01e` 2026-04-27 | `haversine_meters`, `is_vehicle_near_route`, `build_route_shape_cache`, `get_route_shape_cache` |
| `apps/realtime/tasks.py` | `2224e9e` 2026-04-27 | `refresh_iett_mapping(self) -> dict` (line 93), `fetch_iett_positions() -> dict` (line 206); module-level Redis key sabitleri |

**Tests (17 dosya, çalıştırılmadı):** `test_admin_view.py`, `test_asgi.py`, `test_base_adapter.py`, `test_beat_schedule.py`, `test_calendar.py`, `test_channel_layers.py`, `test_consumer_echo.py`, `test_consumer_vehicles.py`, `test_enrich.py`, `test_fetch_task.py`, `test_iett_soap_adapter.py`, `test_integration.py`, `test_locks.py`, `test_mapping_build.py`, `test_rate_limiter.py`, `test_refresh_task.py`, `test_schemas.py`, `test_spatial.py`, `test_views.py`. ROADMAP'a göre son sayım: realtime suite 155/155 yeşil (6h-ii sonu, line 621 ROADMAP).

---

## 2. Celery beat ve Redis kontratı

**Bulgu:** İki schedule entry — `fetch-iett-positions` 60sn, `refresh-iett-mapping` günlük UTC 04:00 (= TR 07:00). 5 Redis key sabit — `MAPPING_CACHE_KEY`, `VEHICLES_ALL_KEY`, `UNMAPPED_COUNT_KEY`, `LAST_FETCH_TS_KEY`, `DAY_TYPE_MISMATCH_COUNT_KEY`. Eski hat-bazlı `vehicles:route:*` pipeline'ı 6c-i'de (`7654d0b`) silindi; tek `vehicles:all` snapshot + `vehicles_all` channel group.

**`config/settings/base.py` lines 164-173:**

```python
CELERY_BEAT_SCHEDULE = {
    "fetch-iett-positions": {
        "task": "apps.realtime.tasks.fetch_iett_positions",
        "schedule": 60.0,  # her 60 saniyede bir (spec §5.7)
    },
    "refresh-iett-mapping": {
        "task": "apps.realtime.tasks.refresh_iett_mapping",
        "schedule": crontab(hour=4, minute=0),  # her gün UTC 04:00 (= TR 07:00)
    },
}
```

**Redis keys (`tasks.py` lines 50-58):**

```
MAPPING_CACHE_KEY            = "iett:mapping:current"
VEHICLES_ALL_KEY             = "vehicles:all"
VEHICLES_ALL_GROUP           = "vehicles_all"           # Channels group
UNMAPPED_COUNT_KEY           = "stats:unmapped_count"
LAST_FETCH_TS_KEY            = "stats:last_fetch_ts"
DAY_TYPE_MISMATCH_COUNT_KEY  = "stats:day_type_mismatch_count"  # 5i-iv
```

**`fetch_iett_positions` payload üretimi (`tasks.py` lines 353-388):**

```python
mapped_count = sum(1 for v in enriched if v.route_id is not None)
unmapped = len(enriched) - mapped_count
redis_client.set(UNMAPPED_COUNT_KEY, unmapped)
...
payload = {
    "type": "vehicles_all_update",
    "timestamp": now_iso,
    "vehicle_count": len(enriched),
    "mapped_count": mapped_count,
    "vehicles": [
        {"id": v.vehicle_id, "lat": v.latitude, "lon": v.longitude,
         "bearing": v.bearing, "speed": v.speed, "route_id": v.route_id}
        for v in enriched
    ],
}
redis_client.set(VEHICLES_ALL_KEY, payload_json, ex=VEHICLES_CACHE_TTL_SECONDS)
async_to_sync(channel_layer.group_send)(
    VEHICLES_ALL_GROUP, {"type": "vehicles.broadcast", "data": payload})
```

`mapped_count` `enriched`'te `route_id is not None` sayım; `vehicle_count` `len(enriched)`. `enrich_with_route_id` (`enrich.py:89`) `route_id = intervals[idx]["hat"]` ile mapping'in `hat_kodu` field'ını döndürür (örn. `"29B"`, `"34BZ"`). **GTFS Route.route_id formatı (`iett:NNNN`) DEĞİL.**

---

## 3. Frontend mapping-aware kod

**Bulgu:** Frontend `route_id` üzerinden filter (panel + focus + popup) yapıyor ve `route_id` formatını `iett:NNNN` (Route.route_id, GTFS pk) bekliyor. Ama backend payload'undaki vehicle'ların `route_id`'si `hat_kodu` ("29B"). **Bu iki form arasında çevrim katmanı yok** — panel'den 29B tıklansa filter `["in", route_id, ["literal", ["iett:1562", ...]]]` ama vehicle'da `route_id="29B"` → eşleşmez. Bus için panel/zoom/focus mode silent fail.

**`websocket.ts` lines 6-12** — payload tipi:
```ts
export interface VehicleSnapshot {
  type: 'vehicles_all_update';
  timestamp: string;
  vehicle_count: number;
  mapped_count: number;
  vehicles: unknown[];
}
```

**`snapshot_store.ts:10`** — Vehicle interface `route_id: string | null`. Optional/null check her tüketicide var:
- `fleet_layer.ts:88`: `if (p.route_id !== null) props.route_id = p.route_id;` — null vehicle properties'e route_id yazmıyor
- `snapshot_store.ts:88`: `if (v.route_id === null || !idSet.has(v.route_id)) continue;`

**"Hat eşlemesi" string'i — popup unmapped dalı:**
- `vehicle_popup.ts:85-87`:
  ```html
  <div class="vehicle-popup__unmapped">
    Bu araç henüz hat eşlemesi yapılmamış
    <div class="vehicle-popup__unmapped-detail">(mapping pipeline güncelleniyor)</div>
  </div>
  ```
  Sadece `meta === null` dalında — `RouteStore.getMeta(props.route_id)` başarısız olduğunda gösterilir.

**Bus panelden çift tıkla zoom — neden çalışmıyor (kod yolu):**

`main.ts:214-225` `focusAndZoom`:
```ts
function focusAndZoom(routeIds: readonly string[]): void {
  routeFocus.setFocus(routeIds);
  const bbox = getRoutesBBox(routeIds) ?? store.getVehicleBBoxForRoutes(routeIds);
  if (bbox) { map.fitBounds(...); } else { showToast('Bu hatta şu an aktif araç yok...'); }
}
```

`store.getVehicleBBoxForRoutes` (`snapshot_store.ts:77-96`) vehicle'ın `v.route_id`'sini `idSet`'le karşılaştırıyor. Panel'den gelen `routeIds` GTFS formatında `["iett:1562", "iett:1564", ...]`; vehicle'da `v.route_id="29B"` (mapping çıktısı). **Set hit yok → count=0 → null dönüyor → toast "araç yok"**. Aynı sorun `fleet-circles` paint expression'ında (`fleet_layer.ts:60`) `['in', ['get','route_id'], ['literal', focused]]` — focused id `iett:1562`, feature property `"29B"` → match yok → tüm bus vehicle opacity 0.2'ye düşüyor (focus aktifken).

**Mapped/unmapped count rolü — `data/websocket.ts:54-58`:** sadece console.log; UI'da `mapped_count`/`vehicle_count` **görsel render'a girmez**, snapshot_store'a push edildikten sonra sadece her vehicle'ın `route_id` alanı tüketiciye gider.

---

## 4. Spec ve roadmap'in Faz 5 tanımı

**Bulgu:** **Faz 5 bus mapping'i kapsamamış.** Spec §5.4 "Tarife-Bazlı Simülasyon (Metro, Marmaray, Vapur)" ve ROADMAP "Faz 5 — Raylı sistem ve vapur simülasyonu" başlıkları net şekilde **canlı veri olmayan** modlara odaklı. İETT bus realtime mapping Faz 2 Adım 5'te ele alındı; "OSM yol snapping" parçası Faz 5'in bonus maddesiydi → Faz 5.5'e taşındı.

**Spec §5.4 ham (lines 510-524):**

```
### 5.4. Tarife-Bazlı Simülasyon (Metro, Marmaray, Vapur)

Canlı konum verisi olmayan modlar için **client-side simülasyon** yapıyoruz:

1. **Sunucu tarafı:** GTFS `stop_times.txt` veriyi yükler, her trip için durak-zaman çiftlerini veritabanına koyar.
2. **API:** `/api/trips/active/?mode=metro&time=now` — şu anda aktif olan tripleri ...
3. **İstemci tarafı:** Her trip için, şu anki zamana göre durak A ile durak B arasında interpolasyon yapar:
   ...
4. **Animasyon:** `requestAnimationFrame` ile sürekli yeniden hesapla
...
**Simülasyon için kritik veri:** `shapes.txt` hat geometrileri olmazsa simülasyon
düz çizgiyle ilerler ... shapes varsa kullan, yoksa duraklar arası OSM'den yol
çekmemiz gerekir (karmaşık, Faz 5'te ele al).
```

§5.4'te "bus mapping" geçmiyor; tek geçiş "OSM'den yol çekmemiz gerekir" → bu Faz 5.5'e ertelendi.

**ROADMAP Faz 5 ham (lines 775-820):**

```
### Faz 5 — Raylı sistem ve vapur simülasyonu ✅
**Durum:** Tamamlandı (2026-05-01).
**Git tag:** `phase-5-complete`

#### Yapılan iş (özet)
- **KM1** — `Calendar` modeli (lite). ...
- **KM2** — `GET /api/trips/active/?mode=...` endpoint. ...
- **KM3-a** — Frontend scheduled metro interpolator. ...
- **KM3-a-fix** — `/api/shapes/{shape_id}/` endpoint + lazy fetch ...
- **KM3-b** — Çoklu mod genişleme. 5 mod paralel polling ...
- **KM3-c** — `import_gtfs --force` idempotency check. ...
- **KM4** — Simulated badge UX ...

#### Bitiş kriterleri
- [x] Metro, Marmaray, vapur araçları 3D haritada hareketli (tarife doğru) ...
- [x] M2 treni Yenikapı→Hacıosman doğru yönde ...
- [x] Vapur Kadıköy-Karaköy hattı Boğaz üstünde gerçek rotayla ...
- [→] İETT OSM snap — Faz 5.5'e taşındı
```

**Karar:** Kullanıcı kullanım sahasında "Faz 5 borç (bus mapping)" demişti (alt-iş g f-polish-3'te ROADMAP commit'i, line 758 civarı: "Faz 5 borç notu: bus realtime mapping pipeline tamamlanması"). Spec/ROADMAP'in tarihsel adlandırması bus mapping'i **Faz 2 Adım 5h/5i**'de ele aldı; "Faz 5" etiketi yanlış kullanılmış. Doğru referans: bus mapping borcu **Faz 2 Adım 5i-v'in açık ucu** (Hipotez X, %52-68 unmapped) + Faz 6 KM1 frontend'in mapping-aware UI ihtiyacı. Faz 5 (raylı/vapur simülasyonu) bus mapping'i kapsamaz.

---

## 5. Faz 2 Adım 5h/5i/5i-v'in bıraktığı izler

**Bulgu:** Son canlı smoke (5i-v, 2026-04-25) **%68.5 unmapped** (4735/6911) ölçtü; "yapısal alt sınır" %52 (3615/6911 fleet_only). Hipotez X test edilmedi (UX pivot kararı sebebiyle). Pivot frontend+backend ikisini de etkiledi: backend hat-bazlı `vehicles:route:*` pipeline silindi (commit `7654d0b`, 6c-i), tek `vehicles:all` modeli geldi.

**Son canlı smoke unmapped (ROADMAP line 417):**
```
status=ok, fetched=6.911, unmapped=4.735 (**%68.5**), routes=532
```

**Yapısal alt sınır (ROADMAP lines 421-427):**
```
- Mapping unique kapı: 4.842
- Mapping'de 21:22 anında aktif kapı: 3.296
- Bugün fleet: 6.911
- Yapısal alt sınır: fleet_only ≥ 6.911 - 3.296 = 3.615 (en az %52)
- Histogram: mapping yoğunluğu 06:00-22:00 platosu, saat-bağlı edge case değil
```

**Hipotez X tanımı (ROADMAP line 429-430):**
```
Fleet endpoint sadece "aktif sefer" değil, "konum gönderen tüm araçlar"
döndürüyor olabilir (parking/idle/garaj dönüşü dahil). Eğer doğruysa %52
yapısal alt sınır aslında ölçüm artefaktı (aktif sefer/aktif sefer
karşılaştırılırsa unmapped %20-30). Test için yarın sabah peak fetch +
hız histogramı analizi gerekirdi, ama UX kararı sebebiyle test gereksiz.
```

**UX pivot kapsamı (ROADMAP lines 432-453):**
- "Eski model (Spec §3.3 hat-merkezli): mapping zorunlu, %52 unmapped görsel olarak eksik araçlar"
- "Yeni model (ham fleet + opsiyonel hat eşleşmesi): 6.911 araç haritada ham nokta"
- **Backend etkisi (5i sonrası, Faz 3 Adım 6c'de uygulandı):** "Faz 3 Adım 6b'de hat-bazlı `SET vehicles:route:{short_name}` + `PUBLISH` pipeline'ı kaldırılıp tek `SET vehicles:all` + `channel_layer.group_send("vehicles_all", ...)` modeline indirgenecek." (line 344)
- **Frontend etkisi:** ROADMAP line 447-452 listeler — ham fleet rendering, popup etkileşim, GET /api/routes/{short_name}/shape, MapLibre polyline tıklama, hat-filtreleme modu opsiyonel.

**Pivot uygulayan commit (vehicles:route:* silen):**
- ROADMAP "Adım 6a–6g kapanış kayıtları" tablosu (line 583): **`7654d0b`** "refactor(realtime): collapse fetch task to vehicles:all + group_send" (Sub-step 6c-i). Aynı tabloda 6c-ii `a6d275a` (docs spec) ve 6d-i `5450e90` (VehicleAllConsumer).

**6h-ii spatial check ek bulgu (ROADMAP line 566):**
```
İETT GTFS feed shape coverage 0/1096 short_name, public feed 496/496.
Canlı veri akışı sadece İETT'den geldiği için cache miss canlı akışta
default durum — ... Spatial check altyapısı korundu, Faz 5+ trip
simülasyonunda public feed'in 496 shape'i etkin olur.
```
Spatial sanity check infra var ama bus için işlevsiz (İETT'de shape yok).

---

## 6. _research/ klasörü ve önceki one-shot script'ler

**Bulgu:** `_research/` mevcut, 15 dosya — Faz 1.5 SOAP/auth keşfi ve 5h öncesi rate-limit ölçümleri. **Hipotez X'i (peak fetch + hız histogramı) test edecek script YOK.** Mapping coverage analizi yapan script de yok; alignment check (`alignment_check.py`) 5b-ii sonrası silinmiş (ROADMAP line 336: "Script `_research/alignment_check.py` silindi (one-shot analiz, sonuç kalıcılaştı)").

**`_research/` içeriği:**

| Dosya | Boyut | Tarih | Açıklama (head'den) |
|---|---:|---|---|
| `arsiv_gorev_today_response.json` | 713 B | 2026-04-23 | API response sample |
| `filo_konum_sample.json` | 51 KB | 2026-04-23 | Fleet endpoint örnek |
| `ibb360_arsiv_gorev_response.json` | 2 B | 2026-04-23 | (boş `[]`) |
| `ibb360_arsiv_gorev_yesterday_response.json` | 25 MB | 2026-04-23 | Bir günlük arşiv |
| `iett-web-servis-v1.2.pdf` | 435 KB | 2026-04-23 | İBB API dokümanı |
| `soap_wsdl.xml` | 29 KB | 2026-04-23 | WSDL discovery |
| `test_29b_tracking.py` | 9.7 KB | 2026-04-19 | 29B özel takip (248 satır) |
| `test_arsiv_gorev_today.py` | 5.3 KB | 2026-04-24 | Arşiv endpoint policy probe |
| `test_filo_hatkodu_check.py` | 6.5 KB | 2026-04-24 | Fleet response HatKodu var mı (185 satır) |
| `test_ibb_token.py` | 6.7 KB | 2026-04-19 | Auth keşif |
| `test_ibb360_arsiv_gorev.py` | 8.7 KB | 2026-04-24 | ibb360 endpoint probe |
| `test_ibb360_arsiv_gorev_yesterday.py` | 8.8 KB | 2026-04-24 | dünün arşivi |
| `test_rate_limit.py` | 5.2 KB | 2026-04-19 | rate-limit window ölçümü |
| `test_refresh_rate.py` | 6.4 KB | 2026-04-19 | refresh interval ölçümü |
| `test_wsdl_discovery.py` | 5.1 KB | 2026-04-24 | WSDL keşif |

**`test_filo_hatkodu_check.py:1-21` özet (read-only):**
```
GetFiloAracKonum_json HatKodu Probe — Faz 1.5 Pre-flight #3
Amaç: Spec §5.3'teki "filo response'unda HatKodu YOK, sadece KapiNo"
iddiasını ampirik olarak doğrula veya çürüt.
```
Bu script Hipotez X'i değil, fleet response field-presence kontrolünü yapıyor. Sonuç ROADMAP'e yansımış ("HatKodu YOK" doğrulandı, mapping pipeline KapiNo→HatKodu lookup üzerine kuruldu).

**Hipotez X için araç listesi (yok):** "peak fetch + hız histogramı" analizi için ne `_research/`'te ne de `apps/realtime/`'da bir script bulundu. ROADMAP line 430: "test gereksiz" denerek atlandı.

**Mapping coverage analizi (yok):** Mevcut/aktif coverage ölçümü için tek araç yok; admin panelinde `unmapped_count` runtime gösterimi var (`admin_views.py:72`) ama analitik / histogram script yok.
