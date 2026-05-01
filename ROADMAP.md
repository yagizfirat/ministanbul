# Mini Istanbul 3D — Roadmap

İstanbul toplu taşıma ağının gerçek zamanlı 3D dijital haritası.
[Mini Tokyo 3D](https://github.com/nagix/mini-tokyo-3d) ilhamlı.

Bu doküman projenin **nihai yol haritasıdır**: ne yapıldı, ne yapılacak,
her fazda hangi kararlar alındı. Her yeni geliştirme oturumunda ilk
okunacak doküman budur.

**Durum:** Faz 1-5 tamamlandı (2026-05-01). Faz 5.5 (OSM yol snapping) ve Faz 6 (cilalama, kurumsal renk + filtreleme öncelikli) paralel açık. Realtime suite 155/155 yeşil, gtfs suite 25/25 yeşil. Toplam 180/180.
**Teknik referans:** [`MINI_ISTANBUL_3D_SPEC.md`](./MINI_ISTANBUL_3D_SPEC.md) (v0.8 — `vehicles:all` pivot)

---

## İçindekiler

1. [Proje özeti](#1-proje-özeti)
2. [Hızlı başlangıç](#2-hızlı-başlangıç)
3. [Proje yapısı](#3-proje-yapısı)
4. [Fazlar](#4-fazlar)
   - [Faz 1 — Veri altyapısı ✅](#faz-1--veri-altyapısı-)
   - [Faz 2 — Canlı veri adaptörü ✅](#faz-2--canlı-veri-adaptörü-)
   - [Faz 3 — WebSocket katmanı ✅](#faz-3--websocket-katmanı-)
   - [Faz 4 — 3D frontend ✅](#faz-4--3d-frontend-)
   - [Faz 5 — Raylı sistem ve vapur simülasyonu ✅](#faz-5--raylı-sistem-ve-vapur-simülasyonu-)
   - [Faz 5.5 — OSM yol snapping ⚪](#faz-55--osm-yol-snapping-)
   - [Faz 6 — Cilalama ⚪](#faz-6--cilalama-)
5. [Veri kaynakları](#5-veri-kaynakları)
6. [Teknoloji seçimleri](#6-teknoloji-seçimleri)
7. [Lisans](#7-lisans)

---

## 1. Proje özeti

İstanbul'daki otobüs, metro, Marmaray ve vapurların konumlarını 3D bir
harita üzerinde canlı olarak gösteren web uygulaması. Otobüsler gerçek
GPS verisiyle hareket eder; raylı sistemler ve vapurlar tarife-bazlı
client-side simülasyonla ilerler. Harita pitch/bearing ile döndürülebilir,
binalar 3D extrusion ile yükseltilmiştir, Boğaz ve tepeler topografik
olarak doğrudur.

**Neden:** Tokyo, Londra, Berlin gibi şehirlerin benzer görselleştirmeleri
var. İstanbul gibi 16 milyon nüfuslu, karmaşık bir toplu taşıma ağı olan
bir metropol için yok. İBB açık veri portalı bu uygulamayı mümkün kılan
verileri yayınlıyor — sadece kimse oturup yapmamış.

Projenin tam kapsamı, mimarisi ve teknik seçimleri spec'tedir.

---

## 2. Hızlı başlangıç

Ön koşul: PostgreSQL 15+ (PostGIS 3 ile), Python 3.11+, Memurai (Windows
için Redis alternatifi, Faz 2'den itibaren).

```bash
cd backend
python -m venv venv
source venv/Scripts/activate        # Windows Git Bash
# .\venv\Scripts\Activate.ps1       # Windows PowerShell

pip install -r requirements/development.txt
cp .env.example .env
# .env içinde: SECRET_KEY, DATABASE_URL, REDIS_URL

python manage.py migrate
python manage.py createsuperuser
python manage.py download_gtfs      # İBB feed'lerini indir (~5 dk)
python manage.py import_gtfs        # PostGIS'e aktar (~4 dk)
python manage.py runserver 127.0.0.1:8010
```

Açıldıktan sonra:

- `http://localhost:8010/preview/` — Leaflet preview (duraklar + hat örnekleri)
- `http://localhost:8010/admin/` — Django admin
- `http://localhost:8010/api/routes/` — REST API

Port 8010 kullanılıyor (diğer projeler 8000/8001'de).

**Faz 3+ — WebSocket katmanı için ek terminal.** Daphne ASGI server,
Django HTTP runserver'la paralel çalışır (Django :8010, Daphne :8011):

```bash
bash backend/scripts/run_daphne.sh    # Linux/macOS/Git Bash
# Windows cmd: backend\scripts\run_daphne.bat
```

Auto-reload yok (Daphne 4.2.1 CLI `--reload` desteklemiyor — 6b-v
deneme, exit code 2). Kod değişikliklerinde Ctrl+C → tekrar başlat.

Faz 3+ ek endpoint'ler:

- `ws://localhost:8011/ws/echo/` — EchoConsumer (WebSocket smoke testi)
- `http://localhost:8010/preview/ws-smoke/` — tarayıcı bağlantı testi sayfası

---

## 3. Proje yapısı

```
mini-istanbul/
├── backend/
│   ├── config/                  Django settings (base/dev/prod)
│   ├── apps/
│   │   ├── core/                Ortak yardımcılar, bbox sabitleri, rate limit tuning
│   │   └── gtfs/                Statik GTFS modelleri + import komutları
│   ├── templates/
│   │   └── preview.html         Leaflet veri doğrulama sayfası (Faz 1)
│   └── requirements/
├── data/gtfs/                   İBB'den indirilen feed'ler (git ignored)
├── _backups/                    pg_dump yedekleri (git ignored)
├── frontend/                    MapLibre + Three.js (Faz 4'te kurulacak)
├── MINI_ISTANBUL_3D_SPEC.md     Teknik referans
├── ROADMAP.md                   Bu doküman
└── ANTIGRAVITY_KICKOFF.md       Agent operasyon notları
```

---

## 4. Fazlar

### Faz 1 — Veri altyapısı ✅

**Durum:** Tamamlandı (2026-04-22)
**Git tag:** `phase-1-complete`

#### Hedef

İBB'nin yayınladığı statik GTFS verilerini indirmek, PostGIS'e aktarmak,
REST API üzerinden sorgulanabilir hale getirmek ve bir preview sayfasında
gözle doğrulamak.

#### Yapılan iş

**Django + PostGIS iskeletisi.** Django 5.1.4 + DRF + drf-gis +
django-filter. Ayrı settings dosyaları (base/development/production).
GeoDjango için Windows'ta GDAL/GEOS bundle yolları `.env`'den okunuyor.

**GTFS modelleri.** Spec §6.2'ye göre: Agency, Route, Stop, Shape, Trip,
StopTime. PostGIS için `Stop.location` PointField ve `Shape.geometry`
LineStringField otomatik GIST index alıyor. StopTime'da `(trip,
stop_sequence)` kompozit B-tree index — hem import hem Faz 5
simülatörünün sıcak yolu.

**`download_gtfs` komutu.** İki ayrı feed'i İBB CKAN API'sinden çeker:
İETT (otobüs) ve Public Transport (metro/Marmaray/vapur/tramvay/füniküler).
Her feed'in SHA-256 hash'i kaydedilir; değişmemişse yeniden indirilmez.

**`import_gtfs` komutu.** Atomik TRUNCATE-and-reload. `gtfs-kit` kullanmak
mümkün olmadı çünkü kütüphane UTF-8 + virgül bekliyor, iki feed de
uymuyor. Ham `pandas.read_csv` + otomatik encoding/delimiter tespiti.

**Veri kalitesi katmanı** (ampirik bulgulara yanıt, detay spec Ek A'da):

- Per-file encoding + delimiter auto-detect (İETT: UTF-8-BOM + noktalı
  virgül; Public: cp1254 + virgül)
- İki aşamalı encoding doğrulama (BOM var ama içerik cp1254 olabiliyor)
- `_sanitize_coord`: Excel'de açılıp kaydedilmiş stops.csv'deki
  `410.191.700.005.564` → `41.0191700005564` Turkish locale artifact
  düzeltmesi (%99.9 recovery)
- İstanbul bbox doğrulaması: `lat [40.7, 41.5]`, `lon [27.95, 29.95]` —
  Silivri köyleri ve Şile kuzeyini içine alacak şekilde kalibre edildi
- `shape_pt_sequence` string sort bug fix (`"1","10","2"` değil, int sort)
- Feed-bazlı `route_id` prefix (`public:1296`, `iett:1296`) — iki feed
  arasında 118 adet route_id çakışması tespit edildi; prefix olmadan
  iett'in upsert'i metroları (M1A/M2/M3/M4/T4/TF1) geçersiz kılıyordu
- Malformed route satırı skip (embedded virgül → 104-char route_id üretmişti)
- Intra-file duplicate route_id tolere (İETT routes.csv'de 4 adet)
- `_safe_int` NaN tolerasyonu (İETT trips.csv'de 451 boş direction_id)
- `_clean_hex` regex-doğrulamalı hex renk (pandas NaN → `"nan"` string
  tuzağına düşmemek için — detay aşağıda)

**REST API.** Spec §6.3'teki tüm endpoint'ler:

- `GET /api/agencies/` — operatörler
- `GET /api/routes/` — hatlar (pagination, `?mode=`, `?has_shape=`)
- `GET /api/routes/{route_id}/` — hat detayı
- `GET /api/routes/{route_id}/stops/` — hatın durakları (sıralı)
- `GET /api/routes/{route_id}/shape/` — GeoJSON LineString
- `GET /api/stops/` — duraklar (pagination, `?bbox=w,s,e,n`)
- `GET /api/stops/{stop_id}/` — durak detayı

Stop serializer Leaflet dostu `{lat, lon}` döner; Shape için drf-gis
`GeoFeatureModelSerializer`.

**Preview sayfası.** `/preview/` — tek dosya Django template. CartoDB
Light raster tiles (spec §5.2'de OpenFreeMap hedefleniyor ama vector-only,
MapLibre migrasyonu Faz 4'te). 22.458 durak `leaflet.markercluster` ile
chunked yükleniyor (5 round-trip). 30 örnek hat paralel fetch ile
polyline olarak çiziliyor, popup'ta hat kısa/uzun adı + mod + operatör.

#### Son bulunan bug (kritik)

`#NAN` renk bug'ı. Public feed'de `route_color` kolonu var ama tüm 499
satır boş. `pandas.read_csv(na_values=[""], dtype=str)` ile boş hücreler
`float('nan')` oluyor, `str(nan)` = `"nan"` — truthy string, `or ""`
guardına takılmıyor. DB'ye `"#NAN"` yazıldı. Leaflet
`L.geoJSON({style:{color:"#NAN"}})` geçersiz SVG stroke üretiyor, browser
sessizce atıyor. Polyline `addLayer` edildi sayılıyor (counter "30 hat
çizildi" diyor), ama görünmüyor.

Neden route_id prefix fix'inden *sonra* ortaya çıktı: Prefix'ten önce iki
feed arasındaki 118 collision yüzünden iett'in last-wins upsert'i tüm
public `#NAN`'lerini `#000000`'a geçiyordu. Prefix collision'ı kırdı,
bozuk değerler ortaya çıktı.

İki katmanlı çözüm:

- Backend: `_clean_hex()` regex-doğrulamalı, NaN/`"nan"`/`"none"` → boş
  string → default `#000000`/`#FFFFFF`
- Frontend: `HEX_RE` guard preview'de, geçersiz renk için turuncu
  fallback + sayaç (gelecekteki benzer bug'lar sessiz başarısızlık değil
  görünür uyarı olsun)

Reimport sonrası 498 bozuk satır temizlendi (DB'de `#NAN` residue = 0).

#### Çıktılar

- **Veritabanı:** Agency=9, Route=9.773, Stop=22.458, Shape=953,
  Trip=150.012, StopTime=1.248.454
- **REST API:** Spec §6.3'teki tüm endpoint'ler çalışıyor
- **Preview sayfası:** 30 polyline + 22.458 durak cluster'ı gözle
  doğrulandı (M4 Kadıköy-Tavşantepe, Marmaray Boğaz geçişi, M2 Avrupa
  yakası)
- **pg_dump backup:** `_backups/pre_color_fix_20260422_214942.dump`
  (13MB, regression durumunda geri dönüş)
- **10 git commit** conventional format'ta
- **Spec Ek A:** 10 maddelik ampirik veri kalitesi bulguları (Faz 1
  geliştirmesinde ortaya çıktı)

#### Faz 1'in bıraktığı sorular (Faz 2+ ele alınacak)

- **İETT'de shapes.csv yok.** Yani 9.279 otobüs hattı için güzergah
  geometrisi İBB tarafından yayınlanmıyor. Faz 5'te OSM Overpass API'den
  stop dizilimine göre yol snapping planlanıyor. Geçici: Faz 4 3D
  haritada otobüsler için duraklar arası düz çizgi.
- **Renk metadata'sı hiç yok.** Public'te kolon var ama boş, İETT'de
  kolon bile yok. Faz 4 3D harita için `short_name → hex` hardcoded map
  gerekecek (M1A, M2, M3, Marmaray, T1-T5, F1-F4 — Metro İstanbul ve
  İETT kurumsal renkleri).

---

### Faz 2 — Canlı veri adaptörü ✅

**Durum:** Tamamlandı (2026-04-26), `d52024a` commit'iyle. Realtime suite 121/121 yeşil.

#### Hedef

İETT SOAP servisinden canlı otobüs konumlarını 60 saniyede bir çekmek, `KapiNo → HatKodu` enrichment sonrası hat bazlı gruplayıp Redis'e yazmak ve hat bazlı pub/sub kanallarına yayınlamak. Rate limit ihlal etmeden sürdürülebilir. Spec §5.7 bu pipeline'ın tam tanımı.

**Önemli:** v0.6.1'deki endişe (KapiNo→HatKodu eşleme kaynağı belirsiz) 2026-04-23 ampirik testleriyle çözüldü. Metot `ibb360.asmx` endpoint'inde mevcut, dün tarihiyle çağrıldığında 55.682 kayıt döner. Detay spec Ek A.11/A.13/A.14.

#### Ön koşullar

- ✅ **Memurai kurulumu** tamamlandı (Memurai 8.1.240, Windows service, port 6379)
- ✅ **RedisInsight (opsiyonel GUI)** — Memurai'ye `localhost:6379` üzerinden bağlanır, pub/sub kanallarını gözle izlemek için faydalı
- ✅ `.env` dosyasında `REDIS_URL=redis://localhost:6379/0` hazır
- ✅ `requirements/base.txt`'te `celery`, `redis`, `django-celery-beat`, `pydantic`

#### Teknik yaklaşım

**Kritik:** Spec §4.2.1'deki ampirik test sonuçlarına uyacağız:

| Parametre | Değer | Kaynak |
|---|---|---|
| Rate limit pencere | ~40 dakika sliding | Ampirik test (200 çağrı, 3s aralık) |
| Pencere kapasitesi | ~72 çağrı | Ampirik |
| Cooldown | ~30 dakika | Ampirik |
| Backend refresh rate | ~60 saniye (ort. 60.3s) | Ampirik |
| Authentication | Anonim (token etkisiz) | Ampirik |
| Fleet endpoint | `https://api.ibb.gov.tr/iett/FiloDurum/SeferGerceklesme.asmx` | Resmi |
| Fleet metod | `GetFiloAracKonum_json()` (~6900 araç, ~1.1MB) | Resmi |
| Arşiv endpoint | `https://api.ibb.gov.tr/iett/ibb/ibb360.asmx` | PDF §10.1 |
| Arşiv metod | `GetIettArsivGorev_json(Tarih)` (yyyyMMdd) | PDF §10.1 + ampirik |

**Strateji:** 60 saniyede bir fleet fetch + client-side interpolation (Mini Tokyo 3D yaklaşımı). Saatte 60 çağrı → pencere kapasitesinin %44'ü kullanılır, %56 tampon kalır.

#### Adım 4 — Adapter çekirdeği (tamamlandı 2026-04-24)

**Commit hash'leri (rebase sonrası):**
- `3fca3af` chore(realtime): scaffold Celery + Redis + realtime app skeleton
- `1a88ed1` feat(realtime): VehiclePosition + IettArsivGorev pydantic schemas
- `6ac2436` feat(realtime): BaseAdapter abstract contract
- `7d2e7cb` feat(realtime): Redis sliding window rate limiter
- `4878b22` feat(realtime): Redis distributed lock with atomic release
- `93f329b` feat(realtime): IETT SOAP parsers for fleet and archive
- `b67ba63` feat(realtime): IettSoapAdapter with rate-limit and lock gates

**Çıktılar:**
- ✅ `apps/realtime/adapters/iett_soap.py` — ham `requests` + string SOAP envelope (zeep kullanılmadı, WSDL strict mode incompatible)
  - `GetFiloAracKonum_json()` wrapper — tüm filo, ~6900 araç, ~1.1MB
  - `GetIettArsivGorev_json(Tarih)` wrapper — `ibb360.asmx` endpoint, `yyyyMMdd` format, `SGOREVDURUM=T` filtresi
- ✅ Pydantic şemalar: `VehiclePosition`, `IettArsivGorev`, `parse_msdate` (Microsoft JSON Date)
- ✅ `BaseAdapter` soyut sınıfı (fetch() contract, health() default, class-level name/source/mode)
- ✅ `SlidingWindowLimiter` (Redis ZSET, 4 state: OK/WARNING/BLOCKED/COOLDOWN, UUID-suffixed member'lar, dual cooldown mechanism)
- ✅ Distributed lock (Redis SETNX + Lua atomic release, per-acquire UUID token)
- ✅ Parser'lar — fleet ve arsiv, summary log pattern'i (`non_T_status`/`null_start`/`null_end`/`malformed` ayrımı)
- ✅ Cassette test suite (`tests/cassettes/` + `_build_from_research.py`): 4 cassette, stratified sampling (550 rows, seed=42)
- ✅ 43 test yeşil, 0.64 saniye — canlı API'ye gitmiyor

**Tasarım kararları not edilenler:**
- Rate limiter'da ZSET member `{timestamp}:{uuid4}` — frozen-clock testlerde collision önleme + production'da race safety
- Cooldown'da hem `SET EX` hem absolute until-timestamp — fakeredis TTL + freezegun uyumsuzluğunu çözmek için
- Distributed lock release Lua script — naive GET-then-DEL yarış riskini engelliyor
- Summary log grep-edilebilir tek satır — ileride ops alerts için load-bearing
- `record_call()` sadece 2xx response sonrası tetikleniyor — ampirik ölçüm de muhtemelen 2xx'leri saymıştı

#### Adım 5 — Celery wiring + hat-merkezli pipeline (sırada)

**5a. Discovery query ✅ (tamamlandı 2026-04-24):**

DB'deki 9.773 Route kaydı spec §3.3 kategorilerine göre sınıflandırıldı. Unique short_name bazında sonuçlar:
- Metro (`^M\d+[A-Z]?$`) → 12 unique / 60 DB row → M1A, M1B, M2, M2A, M3, M3A, M4-M9
- Tramvay (`^T\d+$`) → 4 unique / 5 DB row → T1-T4 (T5 İstanbul'da var ama feed'de yok)
- Füniküler (`^F\d+$`) → 3 unique / 12 DB row → F1-F3 (F4 İstanbul'da var ama feed'de yok)
- Marmaray (`agency_id=2 AND route_type=2`) → 3 unique / 3 DB row → Marmaray, Marmaray1, Marmaray2
- Metrobüs (whitelist) → 10 unique / 113 DB row → whitelist %100 match, 34-prefix'li başka short_name yok
- Vapur (`agency_id=1 AND route_type=4`) → 99 unique / 100 DB row
- Normal İETT otobüs → 1.080 unique / 8.885 DB row

**Toplam sürekli görünür: 131 unique hat.**

Kapsam dışı (MVP'ye dahil edilmeyecek, v1.3'e ertelendi):
- `route_type=9` (Minibus agency) → 317 DB row
- `route_type=10` (Taksi Dolmus agency) → 58 DB row

Detaylar spec §3.3 tablosunda.

**5b. Mapping cache** (`refresh_iett_mapping` Celery task, günlük 04:00):

- [x] **5b-i. build_mapping helper ✅ (tamamlandı 2026-04-24)** — pure function, parsed `IettArsivGorev` list'inden spec §5.7'deki Redis cache JSON yapısını üretir. Commit: `a148239`. 8/8 unit test yeşil (empty, single task, multiple kapi, interval sort, metrobus classification, null kapi skip, inverted interval skip, isoformat). Toplam realtime suite 51/51.

- [x] **5b-ii. Alignment check ✅ (tamamlandı 2026-04-24)** — yesterday dump (55.682 kayıt, 2026-04-22) üstünde SHATKODU ↔ Route.short_name hizalaması ölçüldü. Sonuç: intersection %95.6, orphan 35 hat (tümü Türkçe karakterli sub-variants, normalization %0 kurtarma), DB-only 833 hat (raylı/vapur+opt-in+2 metrobüs). Karar: **mapping formatı sabit**, normalization katmanına gerek yok. Detaylar spec §5.7. Script `_research/alignment_check.py` silindi (one-shot analiz, sonuç kalıcılaştı).

- [x] **5b-iii. `refresh_iett_mapping` Celery task ✅ (tamamlandı 2026-04-25)** — 5h canlı smoke test'te doğrulandı (records=50.600, by_kapi=6.044, active_routes=789, payload 4.2 MB, TTL 28h, atomic SET `iett:mapping:current`). 5i-iii'te `pick_target_date` (holidays-aware) + `target_date`/`day_type` parametreleriyle refactor edildi. Unit testler: adapter mock + fakeredis + `test_refresh_task.py` (5 test), 5i-iii'te 6 calendar test ile birlikte yeşil.

  - [x] **5c. Enrichment helper ✅ (tamamlandı 2026-04-25)** — `apps/realtime/enrich.py`, saf fonksiyon: `enrich_with_route_id(vehicles, mapping) -> list[VehiclePosition]`. `bisect_right(starts, now_ms) - 1` ile O(log n) interval lookup, end inclusive. Mapping eksik (KapiNo yok, boş intervals, ya da `by_kapi` key'i kayıp) veya interval boşluğunda olan araç `route_id=None` ile geçer; sayaç hesaplama 5d fetch task'ın sorumluluğu. `VehiclePosition.frozen=True` olduğu için (schemas.py) input mutate edilemez zaten — helper `model_copy(update={"route_id": ...})` ile yeni objeler döner, çağıran taraf orijinal listeyi temiz tutar. Overlap davranışı: `bisect_right - 1` doğal olarak geç başlayan interval'i seçer (spec §5.7 + bu maddede dokümante; pattern çoksa revize edilir). Commit: `992e272`. 12/12 unit test yeşil (tam match, start/end inclusive, before-first, after-last, interval boşluğu, eksik kapı, boş intervals defansif, overlap, empty vehicles, mutation guard PRESET preserved, corrupt mapping). Toplam realtime suite 68/68, 1.29s.

  - [x] **5d. Fetch task ✅ (tamamlandı 2026-04-25)** — `apps/realtime/tasks.py::fetch_iett_positions`, 60sn beat task. Akış: `IettSoapAdapter.fetch()` → `iett:mapping:current` GET + `json.loads` → `enrich_with_route_id` → `defaultdict(list)` groupby (None bucket düşürülür) → her hat için Redis pipeline (`transaction=False`, single-writer pattern) `SET vehicles:route:{short_name}` (TTL 120sn) + `PUBLISH vehicles:route:{short_name}`. Payload spec §5.3 formatında (`type=route_vehicles_update`, ISO 8601 + Z timestamp, `bearing` pass-through `None` — Faz 4 client interpolator hesaplayacak). Sabitler: `VEHICLES_CACHE_KEY_PREFIX="vehicles:route:"`, `VEHICLES_CACHE_TTL_SECONDS=120`, `UNMAPPED_COUNT_KEY="stats:unmapped_count"` (her tick'te koşulsuz overwrite — heartbeat semantiği). Hata yolları üç ayrı branch: `IettRateLimitViolation` (`error_type=rate_limit_violation`, log.error), `requests.HTTPError` (`error_type=http_error`, log.error), generic `Exception` (`error_type=<class>`, log.exception). Hiçbirinde Celery retry yok — bir sonraki tick 60sn sonra zaten gelecek. Mapping cache miss → boş `{}` mapping ile devam, tüm araçlar unmapped, warning log; admin panel `stats:unmapped_count` üzerinden alarm görür. Stale cache testi (t₀ başarılı SET → t₁ adapter fail → t₂ eski snapshot hâlâ TTL içinde) 5g entegrasyon turunda. Commit: `0551915`. 12/12 unit test yeşil (happy path, multi-route group, unmapped skip, cache miss, adapter failure × 3 branch, empty list, payload format Z+null bearing, SET+PUBLISH dual, multi-route pipeline smoke, unmapped count overwrite). Realtime suite 80/80, 1.18s.

    **Pivot notu (2026-04-26):** Faz 3 Adım 6b'de hat-bazlı `SET vehicles:route:{short_name}` + `PUBLISH` pipeline'ı kaldırılıp tek `SET vehicles:all` + `channel_layer.group_send("vehicles_all", ...)` modeline indirgenecek. Hat-bazlı publish silinmiyor — Faz 5'te metro/marmaray/vapur simülasyonu için geri dönecek.

  - [x] **5e. Celery beat schedule ✅ (tamamlandı 2026-04-25)** — `config/settings/base.py`'a iki schedule entry eklendi: `fetch-iett-positions` (60.0sn float interval) ve `refresh-iett-mapping` (`crontab(hour=4, minute=0)` UTC). `CELERY_TIMEZONE="UTC"` korundu — UTC 04:00 = İstanbul 07:00, dünün arşivi çoktan yazılmış olur (Ek A.13 batch). `CELERY_BEAT_SCHEDULER="django_celery_beat.schedulers:DatabaseScheduler"` da korundu (migration'lar applied); dict bootstrap pattern: ilk startup'ta DB'ye sync, sonraki restart'larda overwrite — Faz 2 (tek-developer, tek-environment) için kabul edilebilir, runtime admin değişikliği gerekirse v1.x'te data migration'a geçilir. Commit: `ab1633a`. 4/4 settings smoke test yeşil (iki entry varlığı, fetch task path + 60.0 interval, refresh task path + `schedule.hour=={4}` `schedule.minute=={0}` sıkı set karşılaştırması — crontab(hour=14) veya crontab(minute=30) regression'larını yakalar, CELERY_TIMEZONE regression guard). Realtime suite 84/84, 1.12s.

  - [x] **5f. Admin "Live Vehicles" sayfası ✅ MVP tamamlandı (2026-04-25)** — `/admin/live-vehicles/`, custom AdminSite URL inject (`apps/realtime/admin.py` monkey-patch + sentinel guard), `apps/realtime/admin_views.py` server-side render, manuel F5 refresh, admin auth otomatik (`admin.site.admin_view()` wrapper). 5 MVP metrik: toplam aktif araç sayısı + top 20 hat breakdown (`vehicles:route:*` aggregation), unmapped count + yüzde (`stats:unmapped_count` / total_seen), mapping cache TTL durumu (Redis TTL semantiği: -2 absent → MISSING, -1 no TTL, >0 hours), son başarılı fetch timestamp (yeni `LAST_FETCH_TS_KEY="stats:last_fetch_ts"` sabit; fetch task'a koşulsuz heartbeat write — sadece success path, cache miss dahil çünkü adapter sağlıklı sayılır), fleet + arsiv rate limit snapshot (`IettSoapAdapter.health()` tek çağrı, status/count/hard/remaining/window_seconds/cooldown). Polish ertelenenler (5h sonrası): 40dk pencere grafik, API health renk göstergesi, mapping drift raporu (refresh task ek Redis key yazması gerek), metrobüs coverage alert (10 whitelist'ten eksik olanlar), orphan SHATKODU listesi. Commit: `651ff4a`. 8 admin test yeşil (auth redirect, authenticated render, total aggregate + ranking, unmapped percent, mapping present TTL display, mapping missing red alarm, rate limit display, empty state). `test_fetch_task.py` happy path'te `last_fetch_ts` bytes + Z suffix assertion eklendi. Realtime suite 92/92, 3.48s.

    **Dev environment notu** (başka bir makinada kurulum için): bu turda iki tek-seferlik PostgreSQL setup adımı gerekti — (1) `ALTER USER mini_istanbul_user CREATEDB` (test DB yaratma izni), (2) `CREATE EXTENSION IF NOT EXISTS postgis` `template1` veritabanına (test DB'leri otomatik PostGIS-ready klonlanır). Önceki tüm realtime testleri fakeredis-only çalıştığı için DB infrastructure tetiklenmemişti; admin testi `Client.force_login` ile gerçek staff user yarattığı için ilk kez Django test DB setup'ı çalıştı. Polish: bu iki adım `docs/SETUP.md`'e (henüz yok) yazılacak. Üçüncü dev gotcha: `LANGUAGE_CODE="tr"` Django float'ları virgül ondalıkla render ediyor (33.3 → 33,3); template'te `{% load l10n %}` + `|unlocalize` filter ile lokalizasyon bypass'lanır (admin sayfası operatör için locale-bağımsız sayı formatı kullanmalı).

  - [x] **5g. Entegrasyon testleri ✅ (tamamlandı 2026-04-25)** — `apps/realtime/tests/test_integration.py`, 4 senaryoluk end-to-end zincir testleri. Yaklaşım: gerçek modüller (adapter parser + enrich + fetch task) tek `fakeredis` instance'ı üzerinden konuşur; mapping `iett:mapping:current` key'ine doğrudan synthetic JSON olarak yazılır (refresh task çağrılmaz çünkü mapping payload format'ı 5b-i'de cassette ile test edildi). Fleet adapter `_parse_fleet_response()` ile gerçek SOAP envelope üzerinden çalıştırılır (`filo_fetch_ok.xml` cassette, 4. adımdan reuse), `adapter.fetch` SimpleNamespace stub ile HTTP/lock/rate-limit bypass'lanır. Senaryolar: (1) **End-to-end chain** — cassette → parser → enrichment → pub/sub, dinamik route assignment (`len(vehicles) >= 8` esneklik, ilk 4+3+1 KapiNo'ya 29B/34BZ/M2 ataması, kalan unmapped); cassette regen edilse de matematik `len(vehicles)`'tan türevsel. (2) **Stale cache** — `freeze_time` + `frozen.tick(seconds=30)`, tick 1 SET (TTL 118-120sn tolerans), tick 2 `RuntimeError`, eski snapshot byte-byte aynı kalır, TTL ~90sn. (3) **Mapping miss → recovery** — tick 1 mapping yok (tüm unmapped, hiç pub, hiç `vehicles:route:*` key), mapping seed, tick 2 aynı adapter snapshot'ı enrichment alır. (4) **Same KapiNo across ticks** — bir araç morning 08:00 → 29B interval, afternoon 16:00 → 15B interval; bisect temporal correctness (geç başlayan kazanır), önceki tick'in 29B snapshot'ı TTL içinde kalır ama yeni tick doğru kanala (15B) yazar. Commit: `83fbc51`. 4/4 yeşil, ilk denemede; tüm realtime suite 96/96, 7.42s.

**5h. Canlı smoke test ✅** (Adım 5'in en sonu, Yağız onayıyla, kontrollü, tek çağrı)

**5h sonucu (2026-04-25, Yağız onayıyla):**

Canlı smoke test 2 API çağrısı kullanılarak yapıldı (rate budget %2.8, ihlal yok):

- **Faz 1 (refresh):** ✅ Başarılı. `iett:mapping:current` Redis'e yazıldı. records=50.600, by_kapi=6.044, active_routes=789, metrobus_coverage=8/10 (34T/34U eksik — pattern), date=2026-04-24 (Cuma), payload=4.2MB, TTL=28h. 16 inverted interval skip edildi (build_mapping warn+skip doğru çalıştı). Ek A.13 H1 (intra-day yazım) lehine güçlü kanıt: Cumartesi sabah Cuma arşivi 50k+ kayıtla dolu döndü.

- **Faz 2 (fetch):** ❌ Mimari bulgu. `fetch_iett_positions` 6911 araç parse etti, status=ok, parse temiz. Ancak enrichment %100 unmapped: 6911/6911 araç `route_id=None`. `vehicles:route:*` Redis key sayısı 0, hiç pub mesajı atılmadı.

**Kök neden:** `build_mapping` interval'leri mutlak epoch ms olarak yazıyor (Cuma 06:00 → 1776686400000 gibi). `enrich_with_route_id` araç timestamp'ini (Cumartesi 13:55 → 1776863726000+) bu interval'lerle bisect ediyor. Cumartesi timestamp'i tüm Cuma interval'lerinin geç sonrası → eşleşme yok.

Bu sadece hafta sonu sorunu değil — her gün geçerli, çünkü mapping hep "dünün absolute epoch ms"i. Ek olarak hafta içi/Cumartesi/Pazar farklı tarifeler olduğundan dün-bugün gün-tipi de tutmuyor (Pazartesi bugün → Pazar mapping = en kötü senaryo).

**Karar:** 5h "design iteration needed" durumunda. Yol 1 (gün-tipi düzeltmesi + HH:MM bazlı mapping + last_same_weekday) yeni sohbette implementation iterasyonu olarak başlayacak. Konum-bazlı doğrulama Faz 4'e ertelendi.

**Smoke test'in değeri:** Tasarım hatasını canlıda yakaladı. Unit testler sentetik epoch'larla geçtiği için bug ancak gerçek dün-arşiv + bugün-fleet karşılaşmasında ortaya çıktı.

### Faz 2 Adım 5i — Tasarım iterasyonu (Yol 1: gün-tipi düzeltmesi) ✅

5h smoke test'inin yakaladığı mimari hata için patch turu. 5 alt-adım:

**5i-i. `build_mapping` refactor** (`apps/realtime/mapping.py`):
- epoch_ms → wall-clock saniye (`start_sec`/`end_sec`, integer)
- Gece geçen görev: `end_sec >= 86400` (extended), aynı kapı aynı liste
- Yeni metadata: `snapshot_date`, `snapshot_day_type` (`weekday`/`saturday`/`sunday`)
- Eski `start_ms`/`end_ms`/`date` field'ları kaldırıldı
- Bitiş: 8 mevcut unit test yeni format'ta yeşil + 1 yeni test (gece geçen interval extended)

**5i-ii. `enrich_with_route_id` refactor** (`apps/realtime/enrich.py`):
- Wall-clock seconds bisect (timestamp Istanbul TZ'ye çevrilir)
- **İmza değişmedi** — saf fonksiyon, dönüş `list[VehiclePosition]` (12 mevcut test korunur)
- Araç-başına overnight detection (`local.hour < 4 + _next_day_type` check)
- Mismatch detection enrich içinde DEĞİL — `tasks.py` tarafında counter'a yazılır
- Bitiş: 12 mevcut test yeşil + 4 yeni (gece geçişi happy path, geçen-gün+sabah <4 doğru kanal, snapshot_day_type yok defansif, snapshot_date yok defansif)

**5i-iii. Holidays paketi + calendar helper + refresh refactor** (BİRLEŞİK; `requirements/base.txt`, `apps/realtime/calendar.py` yeni, `apps/realtime/tasks.py`):
- `holidays>=0.50,<1` paket
- Yeni modül `apps/realtime/calendar.py`: `ISTANBUL_TZ`, `TURKEY_HOLIDAYS`, `get_day_type(date)`, `_next_day_type(snapshot_date_str)`, `pick_target_date(today)` — tatil-aware (today=tatil → Pazar fallback; 7-gün-geri tatil → 14; 14 de tatil → alarm log + Pazar fallback)
- `refresh_iett_mapping`: `pick_target_date` çağırır, `build_mapping(records, target_date, day_type)` çağrısı, return dict'e `target_date`/`day_type` eklenir
- Migration politikası (commit mesajında): yeni format Redis'e overwrite, eski key DEL gerekmez (28h TTL otomatik); deploy günü manuel `refresh_iett_mapping()` + 04:00 beat 24h içinde otomatik geçişi yapar
- Bitiş: 5 mevcut refresh testi yeşil + 6 yeni calendar test (today=tatil→Pazar, today=Cuma + 7gün=tatil→14gün, today=Cuma + 7+14=tatil→alarm+Pazar, today=Pazartesi normal→7gün, today=Cumartesi normal→7gün, get_day_type matrix)

**5i-iv. Admin metrikler + mismatch counter** (`apps/realtime/admin_views.py` + template + tasks.py):
- `fetch_iett_positions`: sample-bazlı mismatch detection, `redis.incr("stats:day_type_mismatch_count")`
- `refresh_iett_mapping`: success path'te `redis.delete("stats:day_type_mismatch_count")` (refresh sonrası reset)
- Admin yeni satırlar: "Mapping kaynağı: weekday (snapshot_date 2026-04-18, 7 gün eski)", "Day-type mismatch count: 0"
- Bitiş: 8 mevcut admin testi yeşil + 2 yeni (snapshot_day_type display, mismatch counter display)

### 5i-v. Yeniden smoke test (2026-04-25 Cumartesi)

**Yapılan canlı çağrılar:** 1 refresh + 1 fetch (rate budget +%2.8, kümülatif %5.6)

**Faz 1 (refresh, target_date=2026-04-18 Cumartesi):**
- status=ok, records_received=41.568, active_routes=680, metrobus_coverage=8/10
- payload_bytes=2.9 MB (eski 5h format 4.4 MB'tan %32 küçük — int seconds avantajı)
- Migration sorunsuz (eski 5h start_ms format → 5i+ start_sec format overwrite)
- snapshot_date=2026-04-18, snapshot_day_type=saturday, TTL ~28h
- Inverted interval skip: 1 kayıt (TM18, build_mapping invariant doğru)
- Overnight intervals: ilk 1000 kapıda 193 (extended end_sec >= 86400 doğru üretildi)
- Mismatch counter refresh sonrası 0 (5i-iv reset doğru çalışıyor)

**Faz 2 (fetch, 2026-04-25 18:22 UTC = 21:22 TRT Cumartesi gece):**
- status=ok, fetched=6.911, unmapped=4.735 (**%68.5**), routes=532
- mismatch_count=0 (saturday=saturday match, sample-based detection sessiz)
- M2 subscriber'da mesaj yok (beklenen: M2 metro, fleet endpoint sadece otobüs)

**B analizi (Redis state, canlı API yok):**
- Mapping unique kapı: 4.842
- Mapping'de 21:22 anında aktif kapı: 3.296
- Bugün fleet: 6.911
- **Yapısal alt sınır:** fleet_only ≥ 6.911 - 3.296 = 3.615 (en az %52)
- mapped_kapis ölçümü artefaktlı (vehicles:route:* TTL=120sn ile düşmüş, B-tekrar gerek yok çünkü UX kararı verildi)
- Histogram: mapping yoğunluğu 06:00-22:00 platosu, saat-bağlı edge case değil

**Hipotez X (test edilmedi, atlandı):**
Fleet endpoint sadece "aktif sefer" değil, "konum gönderen tüm araçlar" döndürüyor olabilir (parking/idle/garaj dönüşü dahil). Eğer doğruysa %52 yapısal alt sınır aslında ölçüm artefaktı (aktif sefer/aktif sefer karşılaştırılırsa unmapped %20-30). Test için yarın sabah peak fetch + hız histogramı analizi gerekirdi, ama UX kararı sebebiyle test gereksiz.

**UX yön değişikliği — 5i kapanış kararı:**

Yağız'ın sezgisel sorusuyla mimari kayma:
- **Eski model (Spec §3.3 hat-merkezli):** Mapping zorunlu, %52 unmapped görsel olarak eksik araçlar
- **Yeni model (ham fleet + opsiyonel hat eşleşmesi):** 6.911 araç haritada ham nokta olarak görünür, tıklamada popup açılır

Popup içeriği:
- Kapı no, hız, yön, son güncelleme zamanı (fleet endpoint, her zaman mevcut)
- Hat bilgisi (mapping'de varsa "29B", yoksa "hat bilinmiyor")
- Hat rotası polyline (GTFS shapes'ten, mapping'den bağımsız)

Yan menüde opsiyonel "hat filtreleme" modu: kullanıcı hat seçerse mapped 2.176 araç renklenir, gerisi dim.

Bu UX'te %52 unmapped artık görsel sürekliliği bozmaz — popup'ta sessiz "hat bilinmiyor" notu olarak yansır. Yol 2 (konum-bazlı doğrulama) gerekli değil. E (14-gün toplu mapping) gerekli değil.

**Faz 4 frontend implementation eklenecek özellikler:**
- Ham fleet rendering (6.911 nokta render)
- Tıklama popup etkileşim katmanı (kapı no, hız, hat info, son güncelleme)
- GET /api/routes/{short_name}/shape endpoint (GTFS shape GeoJSON döner)
- MapLibre polyline layer tıklamada açılır/kapanır
- Yan menü hat-filtreleme modu (opsiyonel, mapped vehicles renklendirilir)

**5i KAPANIŞ — Faz 2 Adım 5 KAPANIŞ.** Kod chain commits: `d2c1748` → `cd94110` → `32dfbb1` → `3a2555c`, kapanış `d52024a`. Realtime suite 121/121 yeşil.

### Faz 2 — Polish backlog

**5j-i. Race-free mismatch counter** ⏭️ v1.x'e ertelendi (5i-iv polish backlog)

Mevcut 5i-iv `redis.set(DAY_TYPE_MISMATCH_COUNT_KEY, 0)` refresh success path'te race window (~1-2sn) içinde fetch tick'inin INCR'ını sıfırlayabilir. Worst case 1-2 mismatch info kaybı, operasyonel etki yok. Race-free alternatif: `last_refresh_ts` + `total_count` - `cached_baseline` pattern. v1.x veya production'da gerçek bir mismatch flow gözleminden sonra ele alınır.

#### Bitiş kriteri

`celery -A config worker` + `celery -A config beat` çalışıyorken:
- 60 saniye sonra Redis CLI `PSUBSCRIBE vehicles:route:*` dinleyince hat bazlı mesajlar akıyor
- `GET iett:mapping:current` → JSON parse edilebilir, `active_routes` listesi dolu
- Admin panelinde 40dk pencere kullanım oranı %56 civarında (~40/72 çağrı)
- Unmapped vehicle oranı %5'in altında
- Network kesilirse veya API 500 dönerse Celery worker çökmüyor, rate limit ihlal edilmiyor

*Bu kriterler Adım 5h'de doğrulandı (rate limit %1.4 kullanım, mapping payload 4.2 MB, fetch task 3 tick boyunca stabil). Adım 5i'deki gün-tipi düzeltmesi sonrası "PSUBSCRIBE vehicles:route:\*" gözlem komutu Faz 3 Adım 6b'de değişecek (`PSUBSCRIBE vehicles:all` veya `MONITOR` ile).*

#### Riskler (güncel)

- **Çözüldü:** ~~KapiNo→HatKodu eşleme kaynağı belirsiz~~ — `ibb360.asmx::GetIettArsivGorev_json` doğrulandı, 55k kayıt test edildi
- **ibb360 rate limit davranışı belirsiz.** SeferGerceklesme ile ayrı sayaç mı paylaşımlı mı test edilmedi. İlk mapping refresh'inde dikkatli gözlem
- **Hafta sonu + Pazartesi davranışı.** Cuma arşivi Pazartesi mapping'i olarak kullanılır — iş günü vs tatil atama farkları olabilir. İlk hafta canlı izlemede doğrulanacak
- **SGOREVDURUM T dışı kodlar.** Güvenli filtre "sadece T" ama %5 veri kaybı. Pattern büyürse yeniden değerlendir
- **Intra-day arşiv boş** (Ek A.13): Bugünün tarihi genelde boş döner, dün kullanıyoruz. Ama Pazartesi sabah `yesterday=Sunday` — cumartesi değil — davranış doğrulanmalı
- **Birden fazla geliştirici aynı endpoint'i test ederse rate limit paylaşılır.** İBB IP bazlı mı kullanıcı bazlı mı bilmiyoruz. Cassette replay disiplini şart

---

### Faz 3 — WebSocket katmanı ✅

**Durum:** Tamamlandı (2026-04-27). Adım 6a-6g ana iş, 6h-i/ii/iii spatial sanity check ve canlı smoke. Realtime suite 155/155 yeşil.

#### Hedef

Redis'teki `vehicles:all` snapshot'ını ve fetch task'ının her tick'te
gönderdiği güncellemeyi WebSocket üzerinden tarayıcıya push eden bir
katman. UX pivot sonrası abonelik modeli sadeleştirildi: client
bağlanır, sunucu tüm filoyu (~6900 araç) tek kanaldan iter. Hat
filtresi frontend'de görsel olarak yapılır, server-side hat-bazlı
kanal yok (Faz 5'te metro/marmaray simülasyonu için geri gelecek).

#### Ön koşullar

- Django Channels 4.x kurulumu
- Daphne ASGI server (port 8011, `.env`'den override edilebilir)
- `.env`'e `CHANNEL_LAYERS` Redis URL'i (önerilen: `db=1`, Celery'den ayrı)

#### Teknik yaklaşım

**Transport:** WebSocket (HTTP long-polling fallback yok — modern tarayıcılar yeter). Port 8011'de Daphne, port 8010'daki Django HTTP'den ayrı process.

**Abonelik modeli (`vehicles:all`, B seçeneği):** Client `ws/vehicles/`
endpoint'ine bağlanır, otomatik olarak `vehicles:all` Channels
group'una eklenir. Bağlantı kurulduğunda ilk render için Redis'teki
son snapshot (`GET vehicles:all`) anında gönderilir. Sonraki her
60sn'lik tick'te fetch task `channel_layer.group_send` ile tüm grup
üyelerine push eder. Client'tan server'a `subscribe`/`unsubscribe`
mesajı YOK — `ping`/`pong` sadece liveness için. Hat-bazlı kanallar
Faz 5'e ertelendi.

#### Yapılacak iş

**Adım 6a — Doc güncelleme ✅ (tamamlandı 2026-04-26, commit `0969415`)**
- ROADMAP'i Faz 2 ✅, Faz 3 🟡 ile günceller
- Spec §5.7'ye pivot notu, §6.4 protokol revizyonu
- Spec versiyon v0.7 → v0.8

**Adım 6b — Channels + Daphne kurulumu ✅ (tamamlandı 2026-04-26)**
*Bu adım önce gelir çünkü 6c (pipeline değişikliği) `channel_layer.group_send` çağrısı yapacak — önce Channels kurulu olmalı.*
- `channels[daphne]` + `channels-redis` requirements'a
- `config/asgi.py` ProtocolTypeRouter
- `CHANNEL_LAYERS` Memurai `db=1` (Celery `db=0`'la ayrı)
- `DAPHNE_PORT=8011` `.env`'den override
- Native Windows Daphne çalıştırma scripti
- Echo consumer + ws-smoke sayfası bağlantı doğrulaması

**Adım 6c — Pipeline `vehicles:all` modeline indirgeme ✅ (tamamlandı 2026-04-26)**
*Önkoşul: 6b (Channels altyapısı) tamamlanmış olmalı.*
- `fetch_iett_positions` task'ında hat-bazlı SET+PUBLISH loop'u silinir
- Yerine tek `SET vehicles:all` (TTL 120s) + tek `group_send`
- Payload formatı: `{type, timestamp, vehicle_count, mapped_count, vehicles[]}`, her vehicle'da `route_id` (null olabilir)
- `test_fetch_task.py` revize, eski hat-bazlı assertion'lar silinir

**Adım 6d — `VehicleAllConsumer` ✅ (tamamlandı 2026-04-26, smoke automation Faz 6'ya ertelendi)**
- `AsyncJsonWebsocketConsumer`, group `"vehicles_all"`
- `connect`: IP cap (max 5/IP), accept, ilk snapshot anında gönder
- `disconnect`: `group_discard`, IP counter decrement
- `receive_json`: `ping`/`pong` sadece, başka komut yok
- `vehicles_all_message` handler: group broadcast → client forward
- Pipeline 6c'deki publish çağrısı `channel_layer.group_send`'e dönüşür

**Adım 6e — REST fallback endpoint'leri ✅ (tamamlandı 2026-04-26)**
- `GET /api/vehicles/live/`: `vehicles:all` key'inden snapshot, stale header

**Adım 6f — Leaflet smoke sayfası ✅ (tamamlandı 2026-04-26)**
- `/preview/realtime/`, WebSocket bağlan, 6900 araç nokta olarak çiz
- HUD: bağlantı, son timestamp, mapped/unmapped breakdown
- Reconnect (basit exponential backoff)

**Adım 6g — Integration test ✅ (tamamlandı 2026-04-26)**
- Cassette fixture → fetch task → `group_send` → `WebsocketCommunicator`
- End-to-end mesaj akışı doğrulaması
- Stale REST senaryosu

**Adım 6h — Canlı smoke + spatial sanity check ✅ (tamamlandı 2026-04-27)**

İlk amaç tek canlı fetch ile 3 tick gözlem ve rate limit %3 altında doğrulama idi. Smoke ortaya bir veri-mantığı boşluğu çıkardı: mapping kaynağı (`KapiNo→HatKodu` zaman-bazlı tablo) bir aracın hangi hatta atanmış olması *gerektiğini* söyler ama gerçekte nerede olduğunu söylemez — araç sefer bitiminde garaja dönmüş ya da molada olabilir, mapping yine onu hat üzerinde gösterir. Bu boşluğu kapatmak için sub-step 6h-i eklendi (spatial sanity check), 6h-ii canlı doğrulama, 6h-iii kapanış olarak yapılandırıldı.

- [x] **6h-i. Spatial sanity check modülü ✅** — `apps/realtime/spatial.py`: lazy-load module-level cache (`get_route_shape_cache()`), numpy vectorized haversine, 500m threshold ile mapped vehicle'ın GTFS shape geometrisinden uzaklaşmış olanlarını `route_id=None`'a degrade eder. Per-vehicle <0.5ms, cold start ~7-10sn (614 route × ~100 nokta). 4 commit ile kod+test ayağa kalktı: `fcf1451` (modül + numpy req), `bc0d5f4` (tasks.py entegrasyon), `b8603d5` (5 unit test), `a07026b` (2 integration test + immutability fix). Suite 147 → 154 yeşil.

- [x] **6h-ii. Canlı smoke + bug + fix-2 ✅** — İlk smoke 6h-i bug'ını ortaya çıkardı: cache miss tüm vehicle'ları null'lıyordu (`mapped_count=0`/tick, 1700+ vehicle defansif null dalında). Teşhis sırasıyla: cache size 496, mapping 614 unique hat, kesişim 0/614; cache key sample'ı sadece raylı (M2, T1) + vapur (BĞZ-2) + uzun isim, hiç İETT kısa kodu yok. Doğrulama sorgusu: **İETT GTFS feed shape coverage 0/1096 short_name, public feed 496/496.** Canlı veri akışı sadece İETT'den geldiği için cache miss canlı akışta default durum — kod bug'ı değil, Faz 1'den beri bilinen veri kısıtının (spec §10 Risk tablosu, "shapes.txt eksikse fallback") spatial check tasarımına yansımamış olması. Fix: cache miss → mapping korunur (graceful skip), cache hit + threshold dışı → eski davranış (null), cache hit + threshold içi → geçer. 3 commit: `2224e9e` (fix tasks.py), `c04d01e` (docs spatial.py docstring), `a316df9` (regression test). Suite 154 → 155 yeşil. Smoke tekrar (3 tick, 21:27-21:28 TR): `mapped_count≈1850`, `spatial_check.skipped_no_shape≈input` (beklenen, İETT shape'siz), `nullified_off_route=0`, `passed=0`. Spatial check altyapısı korundu, Faz 5+ trip simülasyonunda public feed'in 496 shape'i etkin olur.

- [x] **6h-iii. Closure ✅** — Bu blok + spec §10 Risk tablosu güncellemesi + spec 0.7.3 changelog. Faz 3 Adım 6 tamamen kapandı (6a-6g + 6h-i/ii/iii).

#### Adım 6a–6g kapanış kayıtları

**Sub-step commit chain (Faz 3 başlangıcı):**

| Sub-step | Commit | Subject |
|---|---|---|
| 6a | `0969415` | docs: close phase 2, scope phase 3 with vehicles:all model |
| 6b-i | `2cd22cb` | docs(roadmap): swap 6b/6c order to install channels before pipeline rewrite |
| 6b-ii | `f594cb4` | chore(realtime): add channels + daphne, scaffold ASGI router |
| 6b-iii | `8ef66e8` | feat(realtime): wire CHANNEL_LAYERS to memurai db=1 |
| 6b-iv | `9e2065d` | feat(realtime): echo consumer and ws-smoke preview page |
| 6b-v | `bd40316` | chore(realtime): daphne run scripts and log gitignore |
| 6b-vi | `6d536a8` | chore(realtime): close adım 6b, channels infra ready |
| 6c-i | `7654d0b` | refactor(realtime): collapse fetch task to vehicles:all + group_send |
| 6c-ii | `a6d275a` | docs(spec): document vehicles:all payload format |
| 6d-i | `5450e90` | feat(realtime): VehicleAllConsumer with snapshot delivery and IP cap |
| 6d-ii | `eaedf7e` | test(realtime): VehicleAllConsumer test suite |
| 6d-iii | `95cb010` | test(realtime): integration test fetch task → vehicles consumer |
| 6d-iv | `fbfad28` | fix(realtime): VehicleAllConsumer accept-then-group_add order |
| 6e-i | `b15125e` | feat(realtime): vehicles:all REST fallback endpoint |
| 6e-ii | `37e10d7` | test(realtime): vehicles_live REST endpoint test suite |
| 6e-iii | `e684514` | docs(spec): document REST fallback endpoint |
| 6f-i | `23d12d9` | feat(realtime): Leaflet WebSocket smoke preview page |
| 6g-i | `77a3759` | test(realtime): integration tests for REST-WS and SET-broadcast simetry |
| 6h-i-1 | `fcf1451` | feat(realtime): spatial sanity check module |
| 6h-i-2 | `bc0d5f4` | feat(realtime): integrate spatial check into fetch task |
| 6h-i-3 | `b8603d5` | test(realtime): unit tests for spatial sanity check |
| 6h-i-4 | `a07026b` | test(realtime): spatial filter integration tests + immutability fix |
| 6h-ii-1 | `2224e9e` | fix(realtime): spatial check graceful skip on cache miss |
| 6h-ii-2 | `c04d01e` | docs(realtime): note shape data constraint in spatial module |
| 6h-ii-3 | `a316df9` | test(realtime): cache miss preserves mapping invariant |

**Otomasyon smoke (6b-vi, 2026-04-26):**

- `bash backend/scripts/run_daphne.sh` background → ~3 sn'de `Listening on TCP address 127.0.0.1:8011`
- `python backend/scripts/smoke_ws_echo.py` → `OK: echo round-trip 0.7ms` exit 0
- `websockets 15.0.1` (asyncio.client) gerçek network handshake — `WebsocketCommunicator` in-process testleri (4 test) ile birlikte iki katmanı doğruluyor
- Daphne kill: `taskkill /F /PID 2404` (cmd.exe via Bash, MSYS path translation tuzağı için), port 8011 boşaldı

**Reload bulgusu (6b-v):** Daphne 4.2.1 CLI `--reload` desteklemiyor → kod değişikliklerinde manuel restart. ROADMAP risk listesi + `run_daphne.{sh,bat}` yorumlarında dokümante.

**Adım 6c özeti (2026-04-26):** Pipeline pivot tamamlandı — `fetch_iett_positions` artık tek `vehicles:all` snapshot + `channel_layer.group_send` modelinde çalışıyor. Tüketici uyumu (`admin_views.py` + integration testleri) aynı commit'te yapıldı. Spec §5.7 + §6.4 implementation ile hizalandı.

**Adım 6d özeti (2026-04-26):** VehicleAllConsumer canlı, /ws/vehicles/ endpoint client'lara fetch task broadcast'lerini forward ediyor. Implementation 6d-i'de (IP cap + group_add + snapshot delivery + ping/pong + invalid action drop), 9 unit test 6d-ii'de, fetch task → consumer end-to-end integration test 6d-iii'te. 6d-iv'te otomatik smoke script bisect'i Daphne+channels-redis+Memurai+Windows TCP frame transport sorunuyla karşılaştı; root cause bulunamadı, smoke automation Faz 6 polish backlog'a ertelendi. Bisect sırasında keşfedilen consumer order bug'ı (pre-accept group_add handshake bloku) 6d-iv kapsamında fix edildi. Production-equivalent broadcast doğrulaması 6h canlı smoke'da yapılacak.

**Adım 6e özeti (2026-04-26):** REST fallback endpoint canlı, `GET /api/vehicles/live/` son `vehicles:all` snapshot'ını WebSocket payload'ıyla birebir aynı formatta sunar. Cache-Control max-age=60 (tick uyumu), 503 + no-store snapshot yoksa veya bozuksa. WebSocket'a bağlanamayan client'lar için fallback path (eski tarayıcı, captive portal). Spec §6.4'te dokümante edildi.

**Adım 6f özeti (2026-04-26):** Leaflet smoke sayfası canlı, /preview/realtime/ browser'dan WebSocket'a bağlanıp 12 cassette aracını haritada gösteriyor (manuel smoke). UX pivot invariant görsel olarak teyit edildi: mapped (mavi, hat görünür) ve unmapped (kırmızı, "hat: bilinmiyor") ayrımı net. Popup spec §5.7 formatına uyuyor. WebSocket+Daphne+browser kombinasyonu production-equivalent çalıştı — 6d-iv'te otomatik smoke script takıldığımız Daphne+websockets-lib uyumsuzluğu manuel browser akışında görünmüyor (ROADMAP risk satırı 6d-iv'te zaten kayıtlı). Disposable smoke — Faz 4'te frontend framework gelince yenilenir.

**Adım 6g özeti (2026-04-26):** İki yeni invariant integration test'i eklendi. Test 1 (REST↔WS↔SET üçlü payload simetrisi) iki tüketici path'inin ve Redis kaynağının byte-level identical olduğunu doğrular — frontend Faz 4'te WebSocket primary + REST fallback kullanırken semantic gap riski yok. Test 2 (SET↔broadcast simetrisi) pipeline 6c-i K1.A kararının ("tek payload nesnesi") production'da geçerli olduğunu somut kanıtlar. Mevcut testler kapsamı çoğaltılmadı, yalnızca yeni invariant katmanı eklendi.

**Realtime suite final:** 155/155 yeşil (147 + 6h-i'den 7 yeni test + 6h-ii'den 1 regression test). Tüm warning'ler temiz (pytest-asyncio deprecation 6b-iv'te kapatıldı).

**Adım 6h özeti (2026-04-27):** Spatial sanity check eklendi ve canlı smoke ile doğrulandı. Önemli ortaya çıkış: İETT GTFS feed shape coverage **0/1096**, public feed **496/496** — canlı akıştaki spatial check pratik etkisi şu an yok (cache miss, mapping korunur), Faz 5+ trip simülasyonu public feed'in shape'lerini cache'ten kullanmaya başlayınca devreye girer. Bu, kod kararı değil veri kısıtı — spec §10 Risk tablosu "shapes.txt eksikse fallback" politikasıyla tutarlı, §10 ve §14 (0.7.3 changelog) güncellendi.

#### Bitiş kriteri

- Django HTTP (8010) + Daphne (8011) + Celery worker + beat aynı anda çalışıyor
- Browser DevTools → Network → WS: `ws://localhost:8011/ws/vehicles/` bağlantısı 101 Switching Protocols
- Bağlantıdan hemen sonra ~6900 araçlık ilk snapshot mesajı gelir
- Sonraki her 60sn'de yeni snapshot mesajı gelir
- `/api/vehicles/live/` REST fallback aynı snapshot'ı döner (stale değil)
- Realtime suite hedef: 155/155 yeşil ✅ (147 base + spatial check 8 yeni test)

#### Riskler

- **Tek payload boyutu.** 6911 araçlık snapshot ~1MB JSON, sıkıştırma sonrası ~200KB. Daphne default frame buffer (1MB) sınırında — `permessage-deflate` açık olmalı
- **Memurai db ayrılığı.** `db=0` (Celery) ve `db=1` (Channels) ayrı tutulmalı; `FLUSHDB` ile test ederken yanlış db'ye gitme riski
- **Daphne auto-reload yok.** 6b-v deneme: Daphne 4.2.1 CLI `--reload` bayrağını desteklemiyor (exit code 2, "unrecognized arguments"). Kod değişikliklerinde Ctrl+C → tekrar başlat. Prod'da doğru davranış (hot reload prod-safe değil), dev'de ergonomik kayıp kabul edilebilir
- **IP cap yarış koşulu.** Aynı anda 5'i aşan eşzamanlı bağlantı için atomic `INCR` + early reject
- **Smoke automation eksiği (6d-iv → Faz 6).** /ws/vehicles/ endpoint için otomatik smoke script Daphne+channels-redis stack'inde TCP frame transport bug'ı nedeniyle yazılamadı. 6h canlı smoke bu açığı kapsar ama dev döngüsünde "broadcast forwarding katmanını hızlı doğrula" imkânı yok. Faz 6'da channels-redis/daphne sürüm güncellemesi sonrası yeniden ele alınacak
- **`scope["client"]` localhost'ta `127.0.0.1`** — tüm dev bağlantıları aynı IP'den, cap'i development için override edilebilir tut (Faz 6 prod `X-Forwarded-For` desteği ayrı iş)

---

### Faz 4 — 3D frontend ✅

**Durum:** Planlı, Faz 3 bitiminde başlar.
**Tahmini süre:** 3-4 hafta.

#### Hedef

MapLibre GL JS + Three.js + deck.gl ile İstanbul'un 3D haritası. Açılışta **sürekli görünür kategoriler** (metro/tramvay/füniküler/Marmaray/metrobüs/vapur) haritada — polyline'lar + araçlar. Otobüs hatları opt-in panelden seçilir. Araçlar 60 saniye aralıklı snapshot'lara rağmen **akıcı** (60 FPS) hareket ediyor, client-side interpolation sayesinde.

#### Görünüm modeli (Tokyo-vibes, hat-merkezli)

- **Açılış:** Sürekli görünür setin ~50-60 hattı haritada, polyline'lar ve üstlerinde araçlar
- **Sağ panel — "Hatlar":**
  - Arama kutusu (Türkçe fuzzy search, "29b" → 29B bulunur)
  - Mod bazlı gruplar (Metro, Metrobüs, Vapur, ... başlıkları altında)
  - Her hat toggle'lı: seçili → haritada, değil → gizli
  - Sürekli görünür kategoriler varsayılan açık, otobüsler varsayılan kapalı
- **Etkileşim:**
  - Hat tıkla → highlight (opaklık), diğer hatlar sönükleşir (focus mode)
  - Araç tıkla → popup: KapiNo, Plaka, hat, son hız, son güncelleme
  - Durak tıkla → popup: durak adı, geçen hatlar, yaklaşan araçlar
  - Pitch/bearing/zoom ile kamera kontrolü

#### Ön koşullar

- Node.js 20 LTS kurulumu
- `frontend/` dizini Vite + TypeScript projesi olarak init'lenir
- Vite dev server port 5173, `/api/*` Django'ya 8010'a, `/ws/*` Daphne'ye 8011'e proxy

#### Teknik yaklaşım

**Harita motoru seçimi:** MapLibre GL JS 5.x. Spec §5.2'de gerekçeler. OpenFreeMap "bright" stili, tamamen ücretsiz + API key'siz. Mapterhorn DEM raster terrain için.

**3D binalar:** MapLibre `fill-extrusion` + OSM `building` tag'i. Konu-bazlı iyileştirme yok — OSM'de ne kadar detaylı mappe edilmişse o kadar görünür.

**Araçlar:** Three.js custom layer (MapLibre `CustomLayerInterface`). Basit `BoxGeometry` + mod-bazlı renk. Detaylı geometri Faz 6+.

**Sürekli görünür + opt-in yük:**
- Açılışta: ~60 hat polyline + ~500-800 araç (metrobüs canlı + raylı sistem/vapur simüle)
- Opt-in seçimle: her kullanıcı için +1-5 hat × ~9 araç = ~50 ek araç
- Tahmini toplam anlık render: 500-1000 araç, 60-100 polyline
- Three.js `InstancedMesh` (GPU instancing) — 6900 değil ~1000 için de hâlâ uygun

#### Client-side interpolation (kritik)

Bu Faz 4'ün kalbi. İETT verisi 60 saniyede bir geliyor; araçlar ekranda zıplamamalı.

Algoritma (`frontend/src/simulation/bus_interpolator.ts`):

1. T₀ ve T₁ snapshot'ları arasında, her araç için:
   - Aracın hat ID'si (WebSocket mesajında gelen route_id)
   - Hattın `shapes.txt` geometrisini (polyline) yükle — yoksa düz çizgi fallback
   - T₀ konumunu polyline üstündeki en yakın noktaya projekte et (P₀)
   - T₁ konumunu aynı şekilde (P₁)
   - P₀ ile P₁ arasındaki polyline segmentini takip et
2. `requestAnimationFrame` döngüsünde, geçen süre `dt` kadar:
   - Polyline üzerinde P₀'dan P₁'e `dt/60s` oranında ilerle
   - Bearing'i polyline tanjantından hesapla
   - Mesh pozisyonunu güncelle

**Edge case'ler:**
- Araç polyline'dan sapmışsa (GPS hatası, sefer dışı): düz çizgi fallback, log'a not
- T₁ geldiğinde araç T₀-T₁ segmentini henüz tamamlamamışsa: cubic ease ile yeni hedefe kısa geçiş
- İETT hattı GTFS public feed'inde yoksa (İETT'de shapes yok, Faz 5'te OSM snapping sonrası düzelir): düz çizgi

#### Yapılacak iş

1. ✅ Vite + TypeScript init + MapLibre kurulumu
2. ✅ OpenFreeMap style yükleme + 3D binalar + Mapterhorn terrain
3. ⚪ **Hat filtreleme paneli** (Faz 6'dan MVP'ye taşındı — hat-merkezli modelde olmazsa olmaz):
   - `src/ui/RoutePanel.ts` — mod bazlı gruplar, arama, toggle
   - Turkish normalize: ö/ü/ı/ş/ğ/ç → fuzzy search
   - Seçili hat sayısı göstergesi
4. ✅ WebSocket client (`src/data/websocket.ts`):
   - Reconnect (exponential backoff)
   - Hat seçim değişikliğinde `subscribe` gönder (REPLACE semantiği)
   - Per-route `route_vehicles_update` mesajlarını hat state'lerine route et
5. ✅ REST API client (`src/data/api.ts`):
   - `GET /api/routes/?mode=<m>&has_shape=true` — DRF list (`/api/routes/active/`
     yok; backend'de mode filtresi `MODE_TO_ROUTE_TYPE` ile uygulanıyor)
   - `GET /api/routes/{id}/shape/` — polyline (200 GeoJSON Feature veya
     204 No Content; 204 → null tolere edilir)
   - Per-route live: ayrı endpoint yok; global `/api/vehicles/live/` zaten KM1'de
6. ⚪ Three.js custom layer + `InstancedMesh` araç sistemi
7. ⚪ Interpolator (yukarıdaki algoritma)
8. ⚪ Kamera kontrolleri (pitch, bearing, zoom limitleri)
9. ⚪ Durak tıklama → popup (yaklaşan araçlar)
10. ⚪ Hat tıklama → highlight + focus mode
11. ⚪ Araç tıklama → popup
12. ⚪ "Son güncelleme: X saniye önce" UI göstergesi (90sn sarı, 180sn kırmızı)

**Faz 4 kapanışı (2026-05-01):**
KM1-KM3 + KM4-A tamamlandı. KM4-B/C, KM5, KM6 backlog'a ertelendi:
- KM4-B (interpolator integration) ve KM4-C (bearing + edge cases) Faz 5'in raylı sistem/vapur simülasyonuna gömüldü — simüle araçlar zaten `simulation/polyline.ts` üzerinden hareket edecek. Pure algoritma kütüphane olarak hazır, 11/11 Vitest suite ile korunuyor.
- KM5 (InstancedMesh perf) Faz 6 polish'e ertelendi: 6911 araç + 21 polyline + 3D + terrain kombinasyonu Vite + MapLibre default circle layer ile akıcı, FPS sorun yok. İhtiyaç gözlenirse dönülür.
- KM6 (hat filtre paneli, otobüs opt-in dahil) Faz 5 sonrasına ertelendi: simüle metro/Marmaray/vapur araçları geldikten sonra "panelden hat aç → araçlar görünür" deneyimi tam UX olarak kurulabilir.

#### Bitiş kriteri

- `npm run dev` + backend (Django + Daphne + Celery worker + beat) çalışıyor
- `localhost:5173` → İstanbul 3D haritası yükleniyor
- **Açılışta sürekli görünür set haritada:** metrobüs otobüsleri canlı hareket ediyor, metro/tramvay/Marmaray/vapur tarife-bazlı simülasyonla hareket ediyor
- Sağ panelden "29B" seç → haritaya eklendi, kendi araçlarıyla
- Seçimden çıkar → haritadan temizlendi
- Hat tıkla → focus mode (diğerleri sönükleşir)
- Kamera rotasyonu + 3D bina yükseklikleri Boğaz kenarında belirgin
- 60 FPS akıcı interpolation, snapshot geçişleri görünmüyor

#### Riskler

- **Performans çöküşü.** 1000 araç × 60 FPS InstancedMesh doğru kurulmazsa GPU driver darboğazı. Profiler ile erken ölçüm
- **İETT otobüsleri için düz çizgi görsel bozukluk.** Faz 5 OSM snapping'e kadar kabul edilecek geçici durum
- **Mapterhorn DEM tile boyutu.** İlk yüklemede yavaşlık olabilir, lazy load + LOD stratejisi
- **Türkçe fuzzy search hatası.** "İETT 29b" araması karakter normalize olmazsa "29B" bulmaz. `Intl.Collator("tr")` ya da manuel map kullan
- **Hat polyline boyutu.** Bir hat polyline'ı 500-5000 nokta olabilir, 60 hat × ortalama 2000 = 120k nokta sadece polyline'lar. deck.gl layer'a toplu push, hat ekleme/çıkarmada partial update

#### Faz 4 ilerleme

**Adım KM1 özeti (2026-04-28):** Vite + TypeScript scaffold (commit `94cdb50`) ve interpolator v1 + fleet rendering + last-update indicator (commit `4ed462c`) ile Faz 4'ün altyapısı kuruldu. `npm run dev` (5173) + 4 backend pencere (`start_stack.bat`) ile 6911 araç MapLibre haritasında canlı akıyor. Mavi (mapped, 2094) ve kırmızı (unmapped, 4817) renk ayrımı v0.8 UX pivot invariant'ını yansıtıyor. Snapshot store t0/t1 rotation + `requestAnimationFrame` lineer LERP ile 60sn'lik snapshot geçişlerinde gözle "tık" yok. WebSocket primary path, REST polling (5sn timeout) fallback. "Son güncelleme: X sn" göstergesi 90sn sarı / 180sn kırmızı eşikleriyle çalışıyor.

Realtime suite hâlâ 155/155 yeşil — frontend kodu backend kontratlarını tüketiyor, şema değiştirmedi.

**Adım KM2 özeti (2026-04-29):** OpenFreeMap building source-layer üzerine fill-extrusion (cbd5e1→64748b yükseklik gradient'i, opacity 0.85, minzoom 14) ve Mapterhorn DEM raster terrain (terrarium encoding, tileSize 512, exaggeration 1.0) eklendi. Sky atmosphere açık. Initial pose: pitch 45°, bearing -20°, zoom 12, center [29.00, 41.04]. NavigationControl (visualizePitch) sağ üstte, indicator sol üste taşındı (çakışma yok). Mapterhorn endpoint düzeltildi: tiles.mapterhorn.com (recon'da maps. yerine tiles. doğrulandı, terrarium encoding, TileJSON 200 OK). 6911 araç regression yok, pitch eğikken bina+terrain üstünde görünür kalıyor. Realtime suite hâlâ 155/155 yeşil — backend kontrat değişmedi.

**Adım KM3 özeti (2026-04-29):** Açılışta sürekli görünür modların polyline'ları yüklendi: 21 hat (12 metro + 3 Marmaray + 3 tram + 3 funicular). Backend recon'unda `/api/routes/active/` endpoint'inin var olmadığı, gerçek surface'in `/api/routes/?mode=<m>&has_shape=true` (DRF paginated) olduğu doğrulandı; shape endpoint 404 değil **204 No Content** dönüyor (shape'siz hatlar için). `ALWAYS_VISIBLE_MODES = ['subway','tram','funicular']`; subway içinden Marmaray (`short_name.startsWith('Marmaray')`) mor renkle (`#4338ca`), kalan M-hatları lacivert (`#1e40af`) olarak ayrıldı. Tram yeşil (`#16a34a`), funicular turuncu (`#ea580c`). Yeni dosyalar: `src/state/mode_colors.ts`, `src/state/route_store.ts` (add/remove + onRouteAdded/onRouteRemoved listener API — KM6 paneli için hazır), `src/render/route_lines_layer.ts` (tek GeoJSON line layer, color feature property'sinden, line-width 2→6px zoom-bağımlı). 10-batch `Promise.allSettled` ile paralel fetch; 21/0 loaded/skipped. Z-order `beforeId='fleet-circles'` ile garantili: terrain < buildings < route-lines < fleet-circles. Metrobüs polyline'ı **çizilmedi** (İETT GTFS shape'siz, Ek A.10 limit; Faz 5 OSM snapping işi). Vapur (100 hat) **çizilmedi** (KM6 opt-in panel kapsamına alındı; açılışta üst üste turkuaz çizgi karmaşası yok). 6911 araç regression yok, polyline'lar pitch eğikken araçların altında düz yatıyor (terrain takibi yok, MapLibre default — kabul). Realtime suite 155/155 yeşil; backend kontrat değişmedi.

**Adım KM4-A özeti (2026-05-01):** Polyline-aware interpolation algoritması saf modül olarak yazıldı (`frontend/src/simulation/polyline.ts`, 142 satır), 11 Vitest unit testi (`frontend/src/simulation/polyline.test.ts`) ile 11/11 yeşil. Public API: `interpolateAlongPolyline(t0, t1, polyline, alpha) → InterpolatedPose | null`. Yardımcılar export edilmiş: `cumulativeDistances` (Haversine), `snapToPolyline` (equirectangular projeksiyon, metric-correct), `pointAtArcLength` (segment LERP + tanjant bearing). `SNAP_THRESHOLD_M = 500m`, backend Faz 3 6h-i spatial sanity check eşiğiyle uyumlu. Kritik test #11: U-şekilli kavisli polyline ile arc-length midpoint vs chord midpoint farkını numerik olarak kanıtladı — algoritma yolu takip eder, kestirmez. Render entegrasyonu YOK (KM4-B'ye), mevcut `interpolator.ts` v1 LERP fallback için duruyor. Vitest `^2.0.0` devDep, `vitest.config.ts` node env, npm `test`/`test:watch` scriptleri eklendi. Build temiz, tsc hatasız, 1037 kB bundle (KM3'ten +7 kB).

---

### Faz 5 — Raylı sistem ve vapur simülasyonu ✅

**Durum:** Tamamlandı (2026-05-01).
**Git tag:** `phase-5-complete`

#### Yapılan iş (özet)

- **KM1** — `Calendar` modeli (lite). Migration 0002, 52 satır import (49 public + 3 iETT). `CalendarDate` ve `Trip.service_id` FK upgrade Faz 6'ya ertelendi.
- **KM2** — `GET /api/trips/active/?mode=...` endpoint. Mod filter (metro/marmaray/tram/funicular/ferry), Europe/Istanbul TZ, Cache-Control 60s. Tarih filtresi bypass (feed `end_date=20241231` bayat). 15 pytest yeşil.
- **KM3-a** — Frontend scheduled metro interpolator. Stop-level pre-computed projections, route-cached. 9 Vitest yeşil.
- **KM3-a-fix** — `/api/shapes/{shape_id}/` endpoint + lazy fetch + reverse mantığı kaldırıldı. Direction bug'ı çözüldü, shape coverage 30/60'tan 63/63'e çıktı.
- **KM3-b** — Çoklu mod genişleme. 5 mod paralel polling, mode-aware MapLibre paint expression. Perf ölçümü: hiçbir mod 500ms üstünde değil, denormalize borç eklenmedi.
- **KM3-c** — `import_gtfs --force` idempotency check. 7/7 tablo BEFORE=AFTER, 13 saniye reimport, anormal yok.
- **KM4** — Simulated badge UX (sağ üst chip, 5 renkli dot + label + `?` hint tooltip).

#### Bitiş kriterleri

- [x] Metro, Marmaray, vapur araçları 3D haritada hareketli (tarife doğru) — KM3-a + KM3-b
- [x] M2 treni Yenikapı→Hacıosman doğru yönde — KM3-a-fix sonrası kanıtlandı (browser smoke + Vitest "iki yön aynı polyline" regression)
- [x] Vapur Kadıköy-Karaköy hattı Boğaz üstünde gerçek rotayla — KM3-b smoke (31 ferry shape lazy cache, görsel teyit)
- [→] İETT OSM snap — Faz 5.5'e taşındı

#### Discovery raporları

- `docs/phase5_trips_active_discovery.md` — KM2 öncesi keşif
- `docs/phase5_km3a_direction_bug.md` — KM3-a-fix teşhis
- `docs/phase5_km3c_reimport_idempotency.md` — KM3-c kanıt

#### Notlar (gerçek sayılar)

Reimport sonrası DB durumu (KM3-c'de teyitli):
- Agency: 9 — Calendar: 52 — Route: 9 773 — Shape: 953
- Stop: 22 458 — Trip: 150 012 — StopTime: 1 248 454

Discovery raporları daha küçük tahminler vermişti (sadece public feed sayılmıştı). Gerçek toplam (iETT dahil) ×10 büyük.

#### Faz 5 deferred (Faz 6 polish'e taşındı)

- **CalendarDate import** — public feed'de `calendar_dates.csv` yok; iETT'de varsa şu an okunmuyor. Exception override gerekirse Faz 6'da eklenir.
- **Trip.service_id `CharField` → `ForeignKey(Calendar)` upgrade** — Faz 5 KM1'de `service_id` CharField olarak korundu, manuel JOIN ile çalışıyor. FK migration veri-uyum riski taşımıyor (49+3 service'in tamamı Calendar'da mevcut, orphan yok).
- **`route_type=9`** (317 route, 880 trip) ve **`route_type=10`** (58 route, 230 trip) — discovery'de dolmuş/shuttle/ring/hastane servisi gibi görünüyor; GTFS extended kod değil, non-standard İBB değeri. Endpoint whitelist dışı; ne anlama geldikleri Faz 6'da araştırılacak.
- **`frequencies.csv` expansion** — Public feed 2 311 satır, 1 230 distinct trip_id. Marmaray 6/10 trip headway template; subway/tram/ferry'de azınlık. Endpoint v0 explicit `stop_times` üzerinden çalışıyor — frequency-based trip'ler "tek görünür sefer" sınırlamasıyla görünür. Tam expansion Faz 6.
- **Public feed `end_date=20241231` (bayat)** — `download_gtfs` Hash match (İBB tarafında değişmemiş). Endpoint `start_date/end_date` filtresini bypass ediyor (sadece `monday/tuesday/...` flag). Feed yenilenince filtre devreye alınır; o zamana kadar dev/demo modu.
- **Mod toggle UI (canlı / simüle / ikisi birden)** — KM4 sadece bilgilendirici badge yaptı. Kullanıcı modları seçici olarak göstermek isterse Faz 6 polish kapsamında interaction katmanı eklenir.

---

### Faz 5.5 — OSM yol snapping ⚪

**Durum:** Planlı. Faz 5'in "bonus" maddesi olarak kapsamı belirsizdi (pgrouting Windows kurulumu, Overpass rate limit, 270K snap çağrısı ölçeği). Faz 5'i bekletmemek için bağımsız saga'ya taşındı. Faz 6 polish'le paralel yapılabilir veya istenince açılır.

**Tahmini süre:** 1-2 hafta (Windows pgrouting kurulumu + Overpass rate limit keşifleri sonrası netleşir).

#### Hedef

İETT otobüslerinin tarayıcıda yoldan çıkarak hareket etme problemini çözmek. Faz 4 KM1'deki `bus_interpolator.ts` iki GPS snapshot arasını düz çizgi yürütüyor — kıvrımlı yollarda otobüs binaların içinden geçiyor görünüyor. Çözüm: OSM yol ağından gerçek güzergah polyline'ı, `pgr_dijkstra` ile her stop pair için shortest path, snap sonucunu `Shape` tablosuna yaz, frontend bu shape üzerinde yürüsün.

#### Yapılacak iş (alt-fazlar)

- **KM5-a** — pgrouting kurulum + smoke (PostGIS 3.6 + PostgreSQL 15 + Windows uyumu)
- **KM5-b** — Overpass API client (`apps/gtfs/osm_client.py` — rate limit, retry, cache)
- **KM5-c** — OSM yol ağı extraction (İstanbul bbox bölünmesi, `osm_ways` tablosu)
- **KM5-d** — `pgr_dijkstra` proof of concept (1 İETT hatla end-to-end snap, "yol bağlantısı yok" edge case'i)
- **KM5-e** — `python manage.py snap_iett_routes` komutu (batch + progress save + resume)
- **KM5-f** — Snap sonuçlarını `Shape` tablosuna yazma + Trip eşleme
- **KM5-g** — Frontend tarafı: snap'lenmiş shape'leri kullanarak `bus_interpolator.ts` refactor'ü

#### Riskler

- Windows pgrouting kurulum sıkıntılı olabilir (Linux'ta `apt-get install postgresql-15-pgrouting` tek satır, Windows'ta OSGeo4W veya manuel build)
- Overpass API rate limit (10K query/gün IP bazlı) — 270K snap çağrısı için yol ağı önceden cache'lenmeli, snap aşamasında Overpass'a gitmemeli
- 270K dijkstra sorgusu PostgreSQL'de saatler sürer; gerekirse overnight batch + Celery task

#### Bitiş kriteri

- İETT otobüs hareket smoke'ında Beşiktaş kavşak gibi karmaşık geometrili noktalarda otobüs yoldan çıkmıyor
- `Trip.shape_id` İETT trip'lerinin %90+'unda dolu (eskiden NULL'du)
- Performans: snap shape'i lazy fetch + cache (KM3-a-fix pattern'i reuse)

---

### Faz 6 — Cilalama ⚪

**Durum:** Süresiz, kontinü.

#### Hedef

Kullanıcı deneyimi, performans, i18n, mobile responsive. MVP v1.0'ı
yayına hazır hale getirmek.

#### Yapılacak iş

##### KM1 — Kurumsal renk + filtreleme paneli (öncelikli)

Şu anki üç renk katmanı (polyline lacivert tek-mod, scheduled pastel beş-mod, İETT mavi/kırmızı mapped/unmapped) tutarsız. Hedef: İstanbul kurumsal renkleri kullanmak — kullanıcı için çağrışım, demo için profesyonel görsel.

Alt-iş:
- ✅ **Hardcoded renk haritası** (`short_name → hex`) — `frontend/src/styling/route_colors.ts` + 11 Vitest case (commit `a683705`, 2026-05-01). Kanonik hex'ler Wikipedia "Module:Adjacent_stations/Istanbul_Metro" Lua tablosundan: M1A-M14, T1/T4/T5/T6. Marmaray turkuaz (#00B7CD) ve mod fallback'leri (bus #FDC70C, ferry #003E7E) `// TODO: kaynak doğrulaması` notuyla işaretli. T2/T3, F1-F4 ve M1B-vs-M1A ayrımı sonraki turda netleştirilir; o zamana kadar mod fallback'e düşerler. `lighten(hex, amount)` HSL helper'ı alt-iş c için hazır.
- ✅ **Polyline renkleri**: lacivert tek-mod yerine hat-bazlı resmi renk (M2 yeşil, M1A kırmızı, T1 lacivert, …). Mevcut tek-source/tek-layer + data-driven `['get', 'color']` paint zaten Yol B'ye hazırdı; `route_store.add` çağrısında renk lookup'ı `colorForMode` → `getRouteColor(short_name, mode)` swap edildi. `addRouteToMap` imzasına `shortName` eklendi, `RouteFeature.properties` `short_name` alanı taşıyor (alt-iş f hat panelinin filtrelemesi için de hazır). Refactor commit `2f5ec01` (paint pure function `buildRouteLinePaint` + `buildRouteFeature` + short_name propagation), feat commit `bb5ef1f` (KM1 alt-iş b, 2026-05-01). 9 Vitest case eklendi (toplam 56). Funicular F1-F4 hâlâ mod fallback turuncusunda (ROUTE_COLORS'ta hex yok — beklenen; sonraki tur).
- ✅ **Scheduled vehicle renkleri**: polyline'ın açık tonu (M2 koyu yeşil polyline + üstünde açık yeşil nokta). `lighten(getRouteColor(short_name, mode), 0.2)` HSL +0.2L; stroke = orijinal hat rengi (vehicle "halka içinde açık ton" olarak okunur). Eski mod-bazlı 5-pastel `SCHEDULED_VEHICLE_COLORS` paleti kaldırıldı, `state/mode_colors.ts` komple silindi (alt-iş b sonrası colorForMode/MODE_COLORS zaten ölüydü, c'de SCHEDULED_VEHICLE_* da öldü → tek atomik silme). `PreparedTrip` ve `InterpolatedScheduledTrip`'e `short_name` alanı eklendi (pipeline genişletildi). Refactor commit `8f1e858` (paint pure function + short_name propagation), feat commit `2277229` (KM1 alt-iş c, 2026-05-01), chore commit `ff6b51c` (mode_colors.ts sildi). 10 Vitest case eklendi (toplam 66).
- ✅ **İETT vehicle**: kurumsal sarı `#FDC70C`. Mapped/unmapped ayrımı renk yerine border (mapped: 1.5px `#3a2a00` koyu kahve, unmapped: border yok). `circle-stroke-width` paint expression `['case', ['has', 'route_id'], 1.5, 0]`. Eski mavi/kırmızı (mapped/unmapped) palet kaldırıldı — kırmızı "hata" çağrışımını yumuşatma kararı (spec §A.13/A.14 unmapped doğal). Refactor commit `ea66f47` (paint pure function), feat commit `ba796cd` (KM1 alt-iş d, 2026-05-01). 5 Vitest sanity case eklendi (toplam 47).
- ❌ **Chip filtreleme**: KM4 chip'leri tıklanabilir yapılmıştı (commit `07e0084` + `c22ad20`) ama f-polish manuel doğrulamada kullanıcı geri bildirimi: sağ panel mod grupları chip'in info+toggle işlevini ikame etti. **Geri alındı** — `state/mode_visibility.ts`, `state/composite_filter.ts`, `ui/simulated_badge.ts` silindi (commit `0658b2a`). Tarife-bazlı uyarı panel header'ında `?` ikonuyla korundu (alt-iş f-polish madde 4).
- ✅ **Hat-bazlı filtreleme paneli** (sağ panel) — alt-iş f (7 alt-adım f-1..f-6 + manuel f-7 + 4 maddelik polish turu):
  - **Mod gruplandırması** (Metro / Marmaray / Tram / Funicular / Vapur / Otobüs) — 6 grup, bus default kapalı (lazy mount)
  - **Türkçe fuzzy search** (`util/turkish_normalize.ts` + 20 case): ö/ü/ı/ş/ğ/ç normalize, "29b" → 29B, "şiş" → Şişhane match
  - **Her hat toggle'lı**: checkbox + RouteVisibility.toggle, RouteFeature filter
  - **Bulk actions** (header row2): Tümü / Hiçbiri / Reset (Reset = polyline + ferry default)
  - **Bus virtualized list** (`ui/virtual_list.ts` + 10 case): 9275 hat × 40px sabit, ≤20 DOM node, jsdom test
  - **Composite filter** (3 layer): `route-lines`, `scheduled-circles`, `fleet-circles` tek route filter altında
  - **Demojibake** (f-polish madde 1, commit `a324939`): iETT routes UTF-8 mojibake'i import sırasında geri çevirir, ~5346 hat düzeldi
  - **Collapse** (f-polish madde 3, commit `9ab3b02`): collapsed durumda collapse-btn görünür kalır, geri açma yolu
  - **Hint icon** (f-polish madde 4, commit `7a69a1e`): chip kaldırıldı, panel header'ında `?` tooltip
  - Commit zinciri: f-1 keşif raporu, f-2 `a37ff99`, f-3 `296a00d`, f-4 `4e7696d`, f-5 `25c291c`, f-6 (`e10c299`+`281fff7`+`80d1d12`), polish (`a324939`+`0658b2a`+`9ab3b02`+`7a69a1e`)
  - **140 yeşil Vitest** (önceki 75'ten +65: route_visibility 12, turkish_normalize 20, virtual_list 10, route_panel 26, demojibake 11, collapse +1, route_visibility expansion+reset +5, başka), **191 yeşil backend** (180+11 demojibake)

Tahmini süre: 3-4 gün → **gerçek: ~1.5 gün**.

##### KM2 — Mobile responsive (768px breakpoint)

Kontrol panelleri hamburger menüye, popup'lar bottom sheet'e dönsün. Touch events (pinch zoom, two-finger rotate). Chip'ler mobile'da daha küçük + alt köşeye kayma.

##### KM3 — i18n (TR/EN)

i18next entegrasyonu, dil değiştirici, tüm UI string'leri `src/i18n/tr.json` + `en.json`. Tarih/saat locale-aware.

##### KM4 — Performans cilalama

Viewport dışı araçları cull et (mesh update'leri pas geçilsin). Level-of-detail: zoom < 10'da araçları nokta yerine basit point. Three.js `InstancedMesh` (Faz 4 KM5'ten ertelenmişti).

##### KM5 — Diğer borç maddeleri

Faz 5 deferred'tan gelen iş:
- CalendarDate import
- Trip.service_id FK upgrade
- frequencies.csv expansion (Marmaray görünürlüğü için)
- route_type=9/10 araştırması
- Mod toggle UI (KM1'de yapıldı, satır kaldırılır)
- Production deployment dokümanı (Nginx + Daphne + systemd + SSL)
- E2E testler (Playwright)
- Accessibility (klavye, ARIA)
- Durak arama (autocomplete + PostGIS `pg_trgm` fuzzy Turkish)
- Saat çubuğu (opsiyonel, +/- 2 saat kaydırma)
- Landmark GeoJSON'ları (opsiyonel: Ayasofya, Galata Kulesi)

#### Bitiş kriteri

Proje tanım belirsiz kontinü faz. "Yeterli" kararı Yağız tarafından.

---

## 5. Veri kaynakları

### Statik (GTFS)

İki ayrı İBB feed'i, `manage.py download_gtfs` ile CKAN API'den:

- **İETT GTFS** (`iett-gtfs-verisi`) — ~9.300 otobüs hattı, ~15.400
  durak. UTF-8-BOM + noktalı virgül. `shapes.csv` **yok**.
- **Public Transport GTFS** (`public-transport-gtfs-data`) — metro,
  Marmaray, vapur, tramvay, füniküler. cp1254 + virgül. `shapes.csv`
  **var**.

### Canlı (SOAP)

- **İETT filo konumları** —
  `api.ibb.gov.tr/iett/FiloDurum/SeferGerceklesme.asmx`,
  `GetFiloAracKonum_json` metodu. Anonim erişim. Rate limit: ~40dk
  pencere / ~72 çağrı (ampirik).

### Planlı olmayan veri

- **Metro İstanbul REST API'si** tarife + istasyon döner, canlı tren
  konumu **yok**. Faz 5'te tarife-bazlı simülasyon.
- **Marmaray ve vapurlar** için canlı veri **yok**. Aynı şekilde.

### Fallback / ikincil

- `ulasav.csb.gov.tr` — Çevre Bakanlığı ulaşım portalı. İETT Sefer
  Gerçekleşme servisini dataset olarak listeliyor. Test edilmedi,
  sadece İBB API'si çökerse değerlendirilecek.

---

## 6. Teknoloji seçimleri

Detaylı gerekçeler spec §5.2'de.

| Katman | Teknoloji |
|---|---|
| Backend dil | Python 3.11+ |
| Framework | Django 5.1 + DRF + drf-gis + django-filter |
| WebSocket | Django Channels 4.x + Daphne |
| Veritabanı | PostgreSQL 15 + PostGIS 3.6 |
| Cache / Pub-sub / Broker | Redis 7.x (Windows'ta Memurai) |
| Task queue | Celery 5.x + django-celery-beat |
| SOAP | Ham `requests` (zeep WSDL sorunu nedeniyle) |
| Frontend build | Vite + TypeScript |
| Harita | MapLibre GL JS 5.x |
| 3D | Three.js (MapLibre custom layer) |
| Büyük veri katmanları | deck.gl |
| Tile'lar | OpenFreeMap (vector), CartoDB (Faz 1 raster) |
| Terrain | Mapterhorn DEM |
| Test | pytest (backend), Vitest (frontend) |
| Code quality | ruff + black (Python), eslint + prettier (TS) |

---

## 7. Lisans

MIT.

**Veri:**
- © İstanbul Büyükşehir Belediyesi Açık Veri Lisansı (attribution zorunlu)
- © OpenStreetMap katkıda bulunanlar, ODbL
- © OpenFreeMap © OpenMapTiles (Faz 4)
- © Mapterhorn (Faz 4)

Uygulamada görünecek attribution metni:

> Veri: © İstanbul Büyükşehir Belediyesi, © OpenStreetMap katkıda bulunanlar
> Harita: © OpenFreeMap © OpenMapTiles
> Arazi: © Mapterhorn
