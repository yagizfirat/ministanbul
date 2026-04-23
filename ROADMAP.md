# Mini Istanbul 3D — Roadmap

İstanbul toplu taşıma ağının gerçek zamanlı 3D dijital haritası.
[Mini Tokyo 3D](https://github.com/nagix/mini-tokyo-3d) ilhamlı.

Bu doküman projenin **nihai yol haritasıdır**: ne yapıldı, ne yapılacak,
her fazda hangi kararlar alındı. Her yeni geliştirme oturumunda ilk
okunacak doküman budur.

**Durum:** Faz 1 tamamlandı. Faz 2 başlangıcında.
**Teknik referans:** [`MINI_ISTANBUL_3D_SPEC.md`](./MINI_ISTANBUL_3D_SPEC.md)

---

## İçindekiler

1. [Proje özeti](#1-proje-özeti)
2. [Hızlı başlangıç](#2-hızlı-başlangıç)
3. [Proje yapısı](#3-proje-yapısı)
4. [Fazlar](#4-fazlar)
   - [Faz 1 — Veri altyapısı ✅](#faz-1--veri-altyapısı-)
   - [Faz 2 — Canlı veri adaptörü 🟡](#faz-2--canlı-veri-adaptörü-)
   - [Faz 3 — WebSocket katmanı ⚪](#faz-3--websocket-katmanı-)
   - [Faz 4 — 3D frontend ⚪](#faz-4--3d-frontend-)
   - [Faz 5 — Raylı sistem ve vapur simülasyonu ⚪](#faz-5--raylı-sistem-ve-vapur-simülasyonu-)
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

### Faz 2 — Canlı veri adaptörü 🟡

**Durum:** Sırada (Yağız onayı bekleniyor).
**Tahmini süre:** 2-3 hafta.

#### Hedef

İETT SOAP servisinden canlı otobüs konumlarını 60 saniyede bir çekmek,
Redis'e yayınlamak, rate limit ihlal etmeden sürdürülebilir kılmak.

#### Ön koşullar

- **Memurai kurulumu** (Windows için Redis). Redis'in Windows native
  build'i yok; Memurai binary-compatible bir alternatif. Faz 2'nin ilk
  işi bu.
- **RedisInsight (opsiyonel GUI)** — Memurai CLI tabanlı;
  RedisInsight ayrıca indirilebilir, Memurai'ye localhost:6379
  üzerinden bağlanır. Rate limit sayacını ve pub/sub kanalını
  gözle izlemek Faz 2 debug'ında işe yarar.
- `.env` dosyasına `REDIS_URL=redis://localhost:6379/0` eklenmesi
- `requirements/development.txt`'e `celery`, `redis`, `django-celery-beat`
  eklenmesi

#### Teknik yaklaşım

**Kritik:** Spec §4.2.1'deki ampirik test sonuçlarına uyacağız:

| Parametre | Değer | Kaynak |
|---|---|---|
| Rate limit pencere | ~40 dakika sliding | Ampirik test (200 çağrı, 3s aralık) |
| Pencere kapasitesi | ~72 çağrı | Ampirik |
| Cooldown | ~30 dakika | Ampirik |
| Backend refresh rate | ~60 saniye (ort. 60.3s) | Ampirik |
| Authentication | Anonim (token etkisiz) | Ampirik |
| Endpoint | `https://api.ibb.gov.tr/iett/FiloDurum/SeferGerceklesme.asmx` | Resmi |
| Metod | `GetFiloAracKonum_json()` (~6900 araç, ~1.1MB) | Resmi |

**Strateji:** 60 saniyede bir çağrı + client-side interpolation (Mini
Tokyo 3D yaklaşımı). Saatte 60 çağrı → pencere kapasitesinin %44'ü
kullanılır, %56 tampon kalır.

#### Yapılacak iş

1. **`apps/realtime/` app'ini oluştur.** Spec §6.1'deki yapı.

2. **İETT SOAP adaptörü** (`apps/realtime/adapters/iett_soap.py`):
   - **`zeep` kullanma.** zeep-incompatible WSDL (strict mode parse
     başarısız). Ham `requests` + SOAP envelope şablonu kullanılacak.
   - `GetFiloAracKonum_json()` wrapper — tüm filonun tek snapshot'ı
   - ~~`GetIettArsivGorev_json(Tarih)` wrapper~~ — **DOĞRULANMADI,
     mevcut değil.** WSDL discovery (2026-04-23) gösterdi ki bu
     method gateway'de expose edilmiyor ve schema'da tanımı yok
     (spec Ek A.11). Kapı no → hat kodu eşleme kaynağı belirsiz,
     bkz. aşağıdaki risk maddesi.
   - Pydantic `VehiclePosition` schema'sına normalize (spec §5.3)

3. **Rate limit koruması** (kritik, kaybedilmemeli):
   - Redis sliding window sayacı (`ZADD` timestamp'li, `ZREMRANGEBYSCORE`
     40dk önceki temizler, `ZCARD` anlık sayıyı verir)
   - Soft limit 60 (hedef), hard limit 72 (pencere kapasitesi), ikisi
     arasında warning log + Slack-vari alert (şimdilik sadece admin
     panele)
   - HTTP 500 + "Policy Falsified" tespit → 30dk `stale_cache_mode` (TTL
     uzatılır, yeni çağrı yapılmaz)
   - Exponential backoff 1dk → 2dk → 4dk → 8dk → 30dk floor
   - **Distributed lock** (Redis `SETNX` + expire) — birden fazla
     Celery worker aynı anda `GetFiloAracKonum_json` çağırmasın

4. **Celery tasks** (`apps/realtime/tasks.py`):
   - `fetch_iett_fleet` — her 60 saniye (celery beat schedule)
   - `refresh_kapino_hat_mapping` — her gün saat 04:00 (düşük trafik)
   - Sonuçlar Redis'e yazılır (TTL 5dk normal, 45dk hata modunda),
     `vehicles:iett` kanalına pub

5. **Stale cache fallback:** Son başarılı snapshot her zaman cache'te
   tutulur. API fail olursa UI "Veri X saniye önce güncellendi" banner'ı
   gösterir (90s sarı, 180s kırmızı — spec §4.3).

6. **Admin panel:** Yeni "Live Vehicles" sayfası.
   - Son 60 saniyedeki araç sayısı
   - Son çağrının timestamp'i
   - Son 40 dakikadaki çağrı sayısı (grafikle)
   - API health (green/yellow/red)
   - Rate limit kullanım oranı ("44/72 — 28 hak kaldı")

7. **Unit testler:**
   - `test_iett_soap_parser.py` — VCR.py ile kaydedilmiş gerçek
     response'lar üstünde parsing
   - `test_rate_limiter.py` — sliding window, backoff, distributed lock
     edge case'leri
   - `test_stale_cache.py` — cache TTL davranışı, health state transition

#### Bitiş kriteri

`celery -A config worker` + `celery -A config beat` çalışıyorken:

- 60 saniye beklendikten sonra Redis CLI `SUBSCRIBE vehicles:iett`
  dinleyince ~6900 aracın konumu akıyor
- Admin panelinde 40dk pencere kullanım oranı %56 civarında (~40/72 çağrı)
- Network kesilirse veya API 500 dönerse UI "Veri gecikiyor" gösteriyor,
  Celery worker çökmüyor, rate limit ihlal edilmiyor

#### Riskler

- **Birden fazla geliştirici aynı endpoint'i test ederse rate limit
  paylaşılır.** İBB IP bazlı mı kullanıcı bazlı mı bilmiyoruz. Test
  sırasında dikkat, tercihen VCR.py replay.
- **İBB endpoint'i değişirse.** Adaptör katmanı sayesinde tek dosya
  değişir. Fallback: `ulasav.csb.gov.tr`'de listelenmiş ikincil dataset
  (test edilmedi, belirsiz).
- **Kapı no → hat kodu eşleme kaynağı çözülemedi.** 2026-04-23
  ampirik testleri (spec Ek A.11 + A.12 devamı):
  - `GetIettArsivGorev_json` gateway'de mevcut değil
  - `GetFiloAracKonum_json` response'unda HatKodu veya benzer
    hat identifier'ı **yok** (sadece KapiNo, Boylam, Enlem, Hız,
    Garaj, Operator, Plaka, Saat)
  - `GetHatOtoKonum_json` ters yönde çalışıyor, brute force
    86 saat alır

  Faz 2 öncesi tercih edilen yol: (1) İBB resmi PDF'i indirip
  metot kataloğu okumak, (2) GTFS stop/shape proximity heuristic
  ile best-guess hat tahmini üretmek. Detay Ek A.12'de (yazılacak).

---

### Faz 3 — WebSocket katmanı ⚪

**Durum:** Planlı, Faz 2 bitiminde başlar.
**Tahmini süre:** 1-2 hafta.

#### Hedef

Redis'teki canlı araç konumlarını WebSocket üzerinden tarayıcıya push
eden bir katman kurmak. Faz 4'teki 3D frontend için altyapı.

#### Ön koşullar

- Django Channels 4.x kurulumu
- Daphne ASGI server (port 8011)
- `.env`'e `CHANNEL_LAYERS` Redis URL'i

#### Teknik yaklaşım

**Transport:** WebSocket (HTTP long-polling fallback yok — modern
tarayıcılar yeter). Port 8011'de Daphne, port 8010'daki Django HTTP'den
ayrı process.

**Abonelik modeli:** Client-initiated filtering. Tarayıcı bbox ve mode
listesi göndererek abone olur; server sadece o bbox içindeki araçları
push eder. Bu ~6900 aracın tamamını her client'a her saniye göndermenin
önüne geçer.

#### Yapılacak iş

1. **Channels kurulumu** (`config/asgi.py`, `settings/base.py`
   `CHANNEL_LAYERS`)

2. **`VehiclePositionConsumer`** (`apps/realtime/consumers.py`):
   - `connect` — anonim bağlantı kabul, cap: aynı IP'den max 5 eşzamanlı
   - `disconnect` — group'tan çıkar
   - `receive_json` — `subscribe` / `unsubscribe` mesajları
   - `subscribe` handler: bbox + modes doğrular, Redis'ten mevcut
     snapshot'ı anında gönder, group'a ekle
   - Redis pub/sub → group broadcast bridge (spec §6.4 mesaj formatı)

3. **Routing** (`apps/realtime/routing.py`):
   - `ws/vehicles/` URL path

4. **Fallback REST endpoint:** `GET /api/vehicles/live/` — WebSocket
   kurulmazsa (firewall, eski tarayıcı) son snapshot JSON olarak dönsün.

5. **Rate limit per IP:** aşırı `subscribe`/`unsubscribe` döngüsü atan
   bir client'ı throttle et (Django Channels middleware).

#### Bitiş kriteri

- Django HTTP + Daphne + Celery worker + Celery beat aynı anda çalışıyor
- Browser DevTools → Network → WS: `ws://localhost:8011/ws/vehicles/`
  bağlantısı 101 Switching Protocols
- `subscribe` mesajından sonra saniyede araç konumu akıyor, `unsubscribe`
  akışı durduruyor
- Basit Leaflet test sayfası (Faz 4 öncesi smoke test) — noktalar
  haritada hareket ediyor

#### Riskler

- **Port 8011 çakışması.** Kullanıcının diğer projeleri 8001'i alıyor;
  8011 planda ama kullanımda olabilir. `.env`'den override edilebilir
  olsun.
- **Channel layer (Redis) ile Celery Redis aynı instance.** Memory
  basıncı artabilir, özellikle çok client'lı test senaryosunda. DB 0
  Celery, DB 1 Channels önerisi.

---

### Faz 4 — 3D frontend ⚪

**Durum:** Planlı, Faz 3 bitiminde başlar.
**Tahmini süre:** 3-4 hafta.

#### Hedef

MapLibre GL JS + Three.js + deck.gl ile İstanbul'un 3D haritası. Araçlar
60 saniye aralıklı snapshot'lara rağmen **akıcı** (60 FPS) hareket ediyor
— client-side interpolation sayesinde.

#### Ön koşullar

- Node.js 20 LTS kurulumu
- `frontend/` dizini Vite + TypeScript projesi olarak init'lenir
- Vite dev server port 5173, `/api/*` Django'ya 8010'a, `/ws/*` Daphne'ye
  8011'e proxy

#### Teknik yaklaşım

**Harita motoru seçimi:** MapLibre GL JS 5.x. Spec §5.2'de gerekçeler.
OpenFreeMap "bright" stili, tamamen ücretsiz + API key'siz. Mapterhorn
DEM raster terrain için.

**3D binalar:** MapLibre `fill-extrusion` layer'ı + OSM `building` tag'i.
Konu-bazlı iyileştirme yok — OSM'de ne kadar detaylı mappe edilmişse o
kadar görünür.

**Araçlar:** Three.js custom layer (MapLibre `CustomLayerInterface`).
Faz 4 başlangıcında basit `BoxGeometry` + mod-bazlı renk. Detaylı
geometri Faz 6+.

**Veri kutlu sayı:** 6900 otobüs + ~500 metro trenı + ~200 vapur =
~7500 aynı anda hareket eden nesne. Three.js `InstancedMesh` kullanılır
(tek draw call, GPU'da instancing). deck.gl hat çizgileri için.

#### Client-side interpolation (kritik)

Bu Faz 4'ün kalbi. İETT verisi 60 saniyede bir geliyor; araçlar ekranda
zıplamamalı.

Algoritma (`apps/frontend/src/simulation/bus_interpolator.ts`):

1. T₀ ve T₁ snapshot'ları arasında, her araç için:
   - Aracın hattını bul (`KapiNo → HatKodu` eşlemesinden)
   - Hattın `shapes.txt` geometrisini (polyline) yükle — yoksa düz çizgi
     fallback
   - T₀ konumunu polyline üstündeki en yakın noktaya projekte et (P₀)
   - T₁ konumunu aynı şekilde (P₁)
   - P₀ ile P₁ arasındaki polyline segmentini takip et
2. `requestAnimationFrame` döngüsünde, geçen süre `dt` kadar:
   - Polyline üzerinde P₀'dan P₁'e `dt/60s` oranında ilerle
   - Bearing'i polyline tanjantından hesapla
   - Mesh pozisyonunu güncelle

**Edge case'ler:**

- Araç polyline'dan sapmışsa (GPS hatası, sefer dışı): iki konum arası
  düz çizgi fallback, log'a not düş
- T₁ geldiğinde araç T₀-T₁ segmentini henüz tamamlamamışsa: cubic ease ile
  yeni hedefe kısa geçiş (zıplama yok)
- İETT hattı GTFS public feed'inde yoksa (İETT'de shapes yok, Faz 5
  OSM snapping sonrası düzelir): düz çizgi

#### Yapılacak iş

1. Vite + TypeScript init + MapLibre kurulumu
2. OpenFreeMap style yükleme + 3D binalar + Mapterhorn terrain
3. WebSocket client (`apps/frontend/src/data/websocket.ts`) — reconnect,
   bbox-based subscribe on map pan
4. REST API client (`apps/frontend/src/data/api.ts`) — route/shape/stop
   fetching
5. Three.js custom layer + `InstancedMesh` araç sistemi
6. Interpolator (yukarıdaki algoritma)
7. Kamera kontrolleri (pitch, bearing, zoom limitleri)
8. Durak tıklama → popup (yaklaşan araçlar)
9. Hat tıklama → highlight + sadece o hattın araçlarını filtrele
10. "Son güncelleme X saniye önce" health indicator

#### Bitiş kriteri

- `npm run dev` + backend (Django + Daphne + Celery) çalışıyor
- `localhost:5173` → İstanbul 3D haritası yükleniyor
- 6900 otobüs 60 FPS akıcı hareket ediyor — snapshot geçişleri görünmüyor
- M2 metro Yenikapı-Hacıosman hattı boyunca tarifeye uygun ilerliyor
- Kamera rotasyonu + 3D bina yükseklikleri Boğaz kenarında belirgin

#### Riskler

- **Performans çöküşü 7500 mesh'te.** InstancedMesh kullanımı doğru
  kurulmazsa GPU'da driver darboğazı. Profiler ile erken ölçüm.
- **İETT otobüsleri için düz çizgi görsel bozukluk.** Faz 5'e
  (OSM snapping) kadar kabul edilecek geçici durum.
- **Mapterhorn DEM tile boyutu.** İlk yüklemede yavaşlık olabilir,
  lazy load + LOD stratejisi.

---

### Faz 5 — Raylı sistem ve vapur simülasyonu ⚪

**Durum:** Planlı.
**Tahmini süre:** 2 hafta.

#### Hedef

Canlı veri olmayan modları (metro, Marmaray, vapur) tarife-bazlı
simülasyonla hareketli hale getirmek. Bonus: İETT otobüsleri için OSM
route snapping ile gerçek güzergah geometrisi üretmek.

#### Teknik yaklaşım

**Raylı sistemler ve vapur için (GTFS stop_times-driven simülasyon):**

1. Sunucu: `GET /api/trips/active/?mode=metro&time=now`
   - `stop_times.txt` + `calendar.txt` sorgulanır
   - Şu an aktif olan trip'ler (başlangıç zamanı geçmiş, son durağa
     varmamış) döner
   - Her trip için durak-zaman çiftleri listesi
2. İstemci: her aktif trip için sürekli interpolasyon
   - Durak A'dan 14:23:00'de çıktı, durak B'ye 14:25:30'da varıyor
   - Şu an 14:24:15 → yolun %50'sinde
   - A-B arası geometri `shapes.txt`'den; polyline üstünde %50 mesafe
     hesapla
3. `requestAnimationFrame` ile güncelleme (Faz 4 interpolator'ıyla aynı
   runtime)

**UI:** Canlı veri olmayan araçlarda `Simulated` badge — kullanıcı
gerçek gecikmeleri yansıtmadığını bilsin.

**OSM route snapping (İETT otobüsleri için):**

İETT'de `shapes.csv` yok. Duraklar arası düz çizgi kötü görünüyor.
Çözüm: OSM Overpass API'den stop dizilimine göre yol ağını çek, PostGIS
`pgr_dijkstra` ile shortest path.

1. `apps/gtfs/osm_snap.py` yeni modül
2. `python manage.py snap_iett_routes` komutu:
   - Her İETT trip için duraklar sırayla
   - Her ardışık durak çifti arası Overpass ile highway=* yolları çek
   - `pgrouting` shortest path → polyline
   - Cache'le (`Shape` tablosuna kaydet)
3. Maliyet: ~9000 hat × ortalama 30 durak = 270.000 snap çağrısı. Overpass
   rate limit nedeniyle saatlerce sürecek, batch + cache.

#### Yapılacak iş

1. `/api/trips/active/` endpoint
2. Client interpolator'a "scheduled" mode (Faz 4'ün "live" mode'una ek)
3. Simulated badge + UI toggle (canlı / simüle / ikisi birden)
4. Metro / Marmaray / vapur için mod-bazlı renk farklılığı
5. OSM Overpass client + `snap_iett_routes` komutu
6. `pgrouting` extension kurulumu + PostGIS upgrade kontrolü
7. Snap sonuçlarını `Shape` tablosuna yazma + trip eşleme

#### Bitiş kriteri

- Metro, Marmaray, vapur araçları 3D haritada hareketli (tarife doğru)
- M2 treni gerçekten Yenikapı→Hacıosman doğrultusunda, ters değil
- Vapur Kadıköy-Karaköy hattı Boğaz'ın üstünde gerçek rotayla ilerliyor
- İETT otobüslerinin güzergahı OSM snapping sonrası yolları takip ediyor
  (Faz 4'teki düz çizgi gitti)

#### Riskler

- **`pgrouting` PostGIS ile sürüm uyumu.** Kurulum sırasında
  doğrulanacak.
- **Overpass rate limit.** Çalışmaya başlamadan kontrol — belki gece
  cron job + progress save + resume mantığı lazım.
- **Tarife gerçeği yansıtmıyor.** Raylı sistemler aksamalarda tarifenin
  çok dışına çıkabilir. UI'da "Simulated" badge'i net tut.

---

### Faz 6 — Cilalama ⚪

**Durum:** Süresiz, kontinü.

#### Hedef

Kullanıcı deneyimi, performans, i18n, mobile responsive. MVP v1.0'ı
yayına hazır hale getirmek.

#### Yapılacak iş

- **i18next entegrasyonu:** TR / EN dil değiştirici. Tüm UI string'leri
  `src/i18n/tr.json` + `en.json`. Tarih/saat locale-aware.
- **Mobile responsive:** 768px breakpoint. Kontrol panelleri
  hamburger'a, popup'lar bottom sheet'e dönsün. Touch events
  (pinch zoom, two-finger rotate).
- **Performans:** Viewport dışı araçları cull et (bbox filtrelemesi
  zaten WebSocket'te var, ama mesh'ler de update edilmesin). Level-of-
  detail: zoom < 10'da araçları nokta olarak göster.
- **Hardcoded renk map'i:** `short_name → hex` — Metro İstanbul ve İETT
  kurumsal renkleri (Faz 1'de tespit edildi, renk metadata'sı İBB
  feed'lerinde yok).
- **Durak arama:** Autocomplete input, PostGIS `pg_trgm` ile fuzzy
  Turkish search (ö/ü/ı normalize).
- **Hat filtreleme paneli:** Operatöre, moda, renge göre toggle.
- **Saat çubuğu (opsiyonel, v2'ye ertelenebilir):** Şu anki zaman
  +/- 2 saat kaydırılabilir, simülasyon o zamana göre.
- **Landmark GeoJSON'ları (opsiyonel):** Ayasofya, Galata Kulesi vb.
  OSM'de yoksa manuel ekle.
- **Production deployment dokümanı:** Nginx + Daphne + systemd + SSL.
  `docs/DEPLOY.md`.
- **E2E testler (Playwright):** ana user journey'leri.
- **Accessibility:** Klavye navigasyonu, screen reader ARIA label'ları.

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
