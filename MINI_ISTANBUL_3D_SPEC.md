# Mini Istanbul 3D — Teknik Spesifikasyon ve Geliştirme Planı

> İstanbul'un toplu taşıma ağının gerçek zamanlı 3D dijital haritası.
> [Mini Tokyo 3D](https://github.com/nagix/mini-tokyo-3d)'den ilham alınmıştır.

**Versiyon:** 0.3 (Planlama Aşaması — API davranışı ölçüldü, strateji kesinleşti)
**Hedef:** Antigravity agent ile geliştirilecek, Python Django tabanlı bir web uygulaması
**Lisans:** MIT (planlanıyor)
**Statü:** Henüz geliştirmeye başlanmadı — bu doküman geliştirme için tek referanstır

> **v0.3 değişiklikleri (2026-04-19):** İETT SOAP servisine 3 farklı ampirik test yapıldı (token uyumluluğu, dayanıklılık, backend refresh rate). Ölçülen kritik gerçekler:
> - **Rate limit:** ~40 dakikalık sliding window, ~72 istek/pencere. İhlalde ~30 dakika cooldown.
> - **Backend refresh rate:** ~60 saniye (ort. 60.3s, min 57.1s, max 68.1s).
> - **Authentication:** Servis anonim erişime açık, CKAN token'ı SOAP'ta etkisiz (ama zararsız).
>
> v0.2'deki "3 seçenek" belirsizliği kaldırıldı, tek strateji kesinleşti: **60 saniye aralıklı sunucu çağrısı + client-side interpolation**. Detaylar Bölüm 4.2.1 ve 5.4'te.

> **v0.2 değişiklikleri:** İETT resmi web servis dokümanı (v1.5) incelendi. Rate limit ve endpoint yapısı keşfedildi.

---

## 1. Proje Özeti

### Ne yapıyoruz?
İstanbul'daki otobüs, metro, Marmaray ve vapurların gerçek zamanlı konumlarını 3D bir harita üzerinde canlı olarak gösteren web uygulaması. Kullanıcı bir metro istasyonuna tıklayınca yaklaşan trenleri, bir hattı seçince o hattaki tüm araçları, bir durakta bekleyince varış sürelerini görebilir. Harita pitch/bearing ile döndürülebilir, binalar 3D'de yükseltilmiştir, Boğaz ve tepeler topografik olarak doğrudur.

### Niye yapıyoruz?
Tokyo, Londra, Berlin, Singapur gibi şehirlerin böyle görselleştirmeleri var. İstanbul gibi 16 milyon nüfuslu, karmaşık bir toplu taşıma ağı olan bir metropol için yok. İBB açık veri portalı bu tür bir uygulamayı mümkün kılacak verileri yayınlıyor — sadece kimse oturup yapmamış. Proje:

- Açık kaynak olarak yayınlanır, topluluk tarafından geliştirilebilir
- Portföy / showcase niteliğinde bir GIS + full-stack yetkinlik göstergesidir
- İBB'nin açık veri ekosistemine somut bir kullanım örneği sunar

### Kimler kullanacak?
Öncelikli kullanıcılar İstanbullu toplu taşıma kullanıcıları ve turistlerdir. İkincil kullanıcılar ulaşım araştırmacıları, şehir plancıları ve geliştiricilerdir (API erişimiyle).

### Nasıl farklılaşıyor?
Mevcut İETT "Otobüsüm Nerede" uygulaması veriyi 2D sunuyor, turist dostu değil, İngilizce yok, sadece otobüs. Google Maps canlı araç konumu göstermiyor. Moovit var ama 3D değil ve reklam ağırlıklı. Mini Istanbul 3D:

- **3D ve görsel olarak etkileyici**
- **Tüm toplu taşıma modları tek bir yerde**
- **Türkçe + İngilizce**
- **Ücretsiz ve reklamsız**

---

## 2. Kullanıcı Hikâyeleri (User Stories)

### Acil kullanım
**US-1:** Bir durağa gelen kullanıcı, o duraktan geçen bir sonraki araçların kaç dakika sonra geleceğini görmek ister.

**US-2:** Metro istasyonunda bekleyen kullanıcı, trenin şu an nerede olduğunu ve kaç dakika sonra geleceğini görmek ister.

**US-3:** Yolda yürüyen kullanıcı, harita üzerinde en yakın durağı ve oradan geçen hatları görmek ister.

### Keşif
**US-4:** Turist, İstanbul'daki toplu taşıma ağının genel yapısını tek bir ekrana bakarak anlamak ister (hangi metro nereye gidiyor, vapur hatları nereler vs.).

**US-5:** Kullanıcı belirli bir hattı seçip o hat boyunca tüm duraklarını ve şu an hat üzerinde giden araçları görmek ister.

**US-6:** Kullanıcı iki nokta seçip aralarında en uygun toplu taşıma rotasını görmek ister (Faz 6+, opsiyonel).

### Teknik / Meraklı
**US-7:** Geliştirici, uygulamanın sunduğu REST API'yi kullanarak kendi uygulamasına İstanbul toplu taşıma verisi entegre etmek ister.

**US-8:** Araştırmacı, geçmiş bir tarih aralığındaki sefer verilerini indirmek ister (Faz 7+).

---

## 3. Kapsam (Scope)

### İlk sürüm (v1.0) — MVP
**Dahil:**
- **Coğrafi kapsam:** İstanbul geneli (39 ilçe)
- **Ulaşım modları:** İETT otobüsleri, Metro İstanbul tüm hatları (M1-M11, T1-T5, F1-F4), Marmaray, şehir hatları vapurları (İDO)
- **Canlı veri:** Otobüsler gerçek konum, metrolar/vapurlar tarife-bazlı simülasyon (aşağıda açıklanıyor)
- **Harita:** OpenStreetMap tabanlı, 3D bina extrusion, 3D terrain
- **Etkileşim:** Durak tıklama, hat tıklama, araç tıklama, zoom/pan/rotate/pitch
- **Diller:** Türkçe (varsayılan) ve İngilizce
- **Cihaz:** Masaüstü (öncelik) ve mobil tarayıcı (responsive)

**Hariç (ilk sürümde yapılmayacak):**
- Rota planlama (origin→destination)
- Geçmiş veri / zaman kaydırma
- Kullanıcı hesapları, favoriler
- Push bildirimleri, mobil native app
- Minibüs, dolmuş, taksi, özel halk otobüsü hatları
- Trafik verisi, hava durumu entegrasyonu

### Sonraki sürümler (roadmap)
- **v1.1:** Kullanıcı hesabı, favori duraklar/hatlar
- **v1.2:** Rota planlama (OpenTripPlanner entegrasyonu)
- **v1.3:** Minibüs ve dolmuş hatları
- **v1.4:** Landmark 3D modelleri (Ayasofya, Galata Kulesi vb.)
- **v2.0:** Zaman kaydırma, geçmiş veri analizi
- **v2.1:** Mobil native uygulama (opsiyonel)

---

## 4. Veri Kaynakları

### 4.1. Statik GTFS Verileri (Kurulum Sırasında Bir Kez İndirilir)

**Kaynak:** İBB Açık Veri Portalı — https://data.ibb.gov.tr

**İki ayrı veri seti indirilecek:**

1. **İETT GTFS** — https://data.ibb.gov.tr/dataset/iett-gtfs-verisi
   - İETT otobüs hatları, durakları, sefer tarifeleri
   - Standart GTFS formatında (agency.txt, stops.txt, routes.txt, trips.txt, stop_times.txt, shapes.txt, calendar.txt)

2. **Genel Toplu Ulaşım GTFS** — https://data.ibb.gov.tr/dataset/public-transport-gtfs-data
   - Metro, Marmaray, İDO, Turyol, Dentur Avrasya, minibüs, taksi dolmuş hatları

**Not:** GTFS dosyaları kurulum sırasında indirilir ve Django yönetim komutu ile PostGIS veritabanına aktarılır. Geliştirici lokalde `python manage.py import_gtfs` komutunu çalıştırır.

### 4.2. Canlı Veri API'leri

**4.2.1. İETT Canlı Otobüs Konumları (SOAP servisleri)**

İETT, çeşitli SOAP web servisleri üzerinden veri yayınlıyor. **Resmi dokümantasyon:** [İETT Web Servis Kullanım Dokümanı v1.5](https://data.ibb.gov.tr/dataset/3e32bb5d-2936-41eb-bdc7-65b843487e99/resource/6821f452-f6ff-49e9-940a-d4ebfc78f03e/download/iett-web-servis-kullanm-dokumanv.1.2.pdf) (İBB tarafından yayınlanmış PDF).

**Canlı filo konumları için iki endpoint:**

| Metod | Parametre | Ne döndürür? |
|---|---|---|
| `GetFiloAracKonum_json()` | yok | **Tüm aktif filonun** konumları (~6900 araç tek çağrıda, ~1.1 MB payload) — Akyolbil servisi |
| `GetHatOtoKonum_json(HatNo)` | hat kodu (zorunlu) | Belirli bir hattaki araçların konumları |

**Endpoint:** `https://api.ibb.gov.tr/iett/FiloDurum/SeferGerceklesme.asmx`

**Authentication:** Servis **anonim erişime açık**. data.ibb.gov.tr'de hesap açıp API token almak SOAP servisi için bir etki yaratmıyor (test edildi). Token ile veya tokensız aynı sonuç döner.

#### Ampirik Test Sonuçları (2026-04-19)

Geliştirmeye başlamadan önce servisi üç ayrı testle ölçtük. Sonuçlar stratejimizi belirliyor:

**Test 1 — Token uyumluluğu:**
- CKAN API token'ı header'da, query string'de, hiç yok — üçü de aynı sonucu verdi
- **Çıkarım:** SOAP servisi authentication gerektirmiyor

**Test 2 — Dayanıklılık (200 çağrı, 3 saniye aralık):**
- İlk 72 istek başarılı (~5 dakika içinde, 16:14:49 → 16:20:01)
- 73. istekten itibaren HTTP 500 + "Policy Falsified" (rate limit tetiklendi)
- Yeniden açılma: 17:00:33 (ilk block'tan ~40 dakika sonra)
- **Çıkarım:** Rate limit **saat bazlı değil, ~40 dakikalık sliding window**. Pencere başına ~72 istek hakkı var. İhlalde ~30 dakika cooldown.

**Test 3 — Backend refresh rate (10 saniye aralıklı 30 snapshot):**
- Yeni veri gelme aralıkları: 57.1s, 57.7s, 58.3s, 68.1s
- Ortalama: **60.3 saniye** (min 57.1, max 68.1)
- **Çıkarım:** Backend her ~60 saniyede bir veri yayınlıyor. Daha sık çağrı yapmak aynı veriyi döndürür (bandwidth ve rate limit israfı).

#### Kesinleşmiş Strateji: 60 saniyede bir çağrı + client-side interpolation

**Sunucu tarafı:**
- Celery beat görevi **her 60 saniyede** `GetFiloAracKonum_json()` çağırır
- Sonuç Redis'e yazılır (TTL 5 dakika), WebSocket üzerinden frontend'e yayınlanır
- **Rate limit marjı:** Saatte 60 çağrı yapılır, 40-dk pencerede 40 çağrı. Güvenli marj: pencere kapasitesinin %44'ü kullanılır, %56 boşta kalır (API arıza/retry senaryoları için tampon).
- Savunma katmanları:
  1. Redis sayacı: son 40 dakikadaki çağrıları say, 60'a yaklaşırsa DURAKLA
  2. Distributed lock (Redis SETNX): birden fazla worker instance aynı anda çağrı yapmasın
  3. 429 veya 500 hata alınırsa exponential backoff (1dk, 2dk, 4dk, 8dk — en az 30dk)
  4. Stale cache fallback: son başarılı veri 5 dakika cache'te tutulur, API fail olursa gösterilir

**İstemci tarafı:**
- WebSocket üzerinden 60 saniyede bir yeni konum snapshot'ı alınır
- Her araç için **konum interpolasyonu** yapılır:
  - T₀ (önceki snapshot) ve T₁ (yeni snapshot) konumları arasında
  - Aracın ait olduğu hat `shapes.txt` geometrisine projekte edilir (polyline üzerinde closest point)
  - `requestAnimationFrame` ile 60 FPS akıcı animasyon
- Kullanıcı "canlı harita" algılar, gerçekte 60 saniye aralıklarla veri geliyor
- **Bu Mini Tokyo 3D'nin yaklaşımıdır.** Tokyo'da veri 15-30s aralıklarla gelir, aynı interpolation stratejisi uygulanır.

**Neden bu kombinasyon?**
- Daha sık çağrı yapmak → aynı veri döner, boşa trafik
- Daha az sık çağrı → araç pozisyonları eskir, interpolation hataları büyür
- Interpolation yok → araçlar 60 saniyede bir "zıplar", görsel bozulur
- Bu strateji **hem performans hem kullanıcı deneyimi açısından optimum**

#### Gelecek İyileştirme Notları

- **İBB'ye API key başvurusu:** data.ibb.gov.tr'de hesap açıldı (test amaçlı). SOAP servisinde etkisiz olduğu doğrulandı. Gelecekte İBB rate limit'ini artıran bir authenticated tier sunarsa düşünülebilir, ama mevcut durumda gerek yok.
- **Topluluk wrapper (hakanatak/dataibbgovtr, mekansal.herokuapp.com):** Mevcut SOAP servisinin üzerine yazılmış, rate limit sorununu çözmüyor. Referans olarak incelendi.

**Dönen veri formatı (`GetFiloAracKonum_json`):**

```json
{
  "Operator": "IETT",
  "Garaj": "HASANPASAGARAJI",
  "KapiNo": "C-231",
  "Saat": "14:23:45",
  "Boylam": "29.1032215",
  "Enlem": "41.0488515",
  "Hiz": "24",
  "Plaka": "34 HO 1234"
}
```

**ÖNEMLİ:** Bu veride **hat kodu YOK** — sadece `KapiNo`. Hat bilgisi başka servisten alınır:
- `GetIettArsivGorev_json(Tarih)` → gün başında bir kez çağrılır, `KapiNo → HatKodu` eşleme tablosu Redis'te cache'lenir
- Bazı araçların `Operator: OHO` gibi 3. parti operatör değerleri olabilir — bu araçlar İETT hattına atanmamış olabilir, UI'da "genel filo" olarak gösterilir

**Diğer faydalı İETT servisleri:**

| Servis | Endpoint | Ne işe yarar? |
|---|---|---|
| Hat-Durak-Güzergah | `UlasimAnaVeri/HatDurakGuzergah.asmx` | Durak, hat, garaj meta verisi (GTFS'e tamamlayıcı) |
| Duyurular | `UlasimDinamikVeri/Duyurular.asmx` | Hat kesintileri, anlık duyurular |
| Planlanan Sefer Saati | `UlasimAnaVeri/PlanlananSeferSaati.asmx` | Hat kalkış saatleri (iş günü / cumartesi / pazar) |
| İBB 360 Arşiv | `ibb/ibb360.asmx` | Geçmiş görev ve yolculuk verisi (Faz 7+) |
| Araç Özellikleri | `AracAnaVeri/AracOzellik.asmx` | Yakıt tüketimi (data analiz için) |

**Not:** Bu diğer servisler ayrı SOAP endpoint'leri, `SeferGerceklesme.asmx` ile rate limit paylaşımı **test edilmedi**. Muhtemelen ayrı ama doğrulanmalı. Güvenli yaklaşım: her servise kendi rate limit mantığı.

**Referans implementasyonlar:**
- [hakanatak/dataibbgovtr_python](https://github.com/hakanatak/dataibbgovtr_python) — Python, SOAP→GeoJSON wrapper
- [burakbayramli blog yazısı](https://burakbayramli.github.io/dersblog/sk/2023/01/iett-ibb-otobus-verisi.html) — `zeep` kullanım örnekleri
- [AydinAdn/IBB.Api](https://github.com/AydinAdn/IBB.Api) — .NET client kütüphanesi (endpoint referansı için)

**WSDL parse sorunu:** Python `zeep` kütüphanesi İETT'nin WSDL'ini strict modda parse ederken `GetBozukSatih_XMLAuthHeader` tanımı nedeniyle hata veriyor. Çözümler:
1. `zeep.Client(wsdl=..., strict=False)` ile başlat
2. Veya `zeep`'i tamamen atlayıp doğrudan `requests` ile ham SOAP envelope gönder (test script'lerinde kullanıldığı yöntem)

Geliştirmede 2. yöntem önerilir (bağımlılık az, hata daha az).

**4.2.2. Metro İstanbul REST API**

Metro İstanbul, REST endpoint'leri üzerinden aşağıdaki verileri veriyor:
- Base URL: `https://api.ibb.gov.tr/MetroIstanbul/api/MetroMobile/V2/`
- Endpoint'ler (data.ibb.gov.tr'de dokümante edilmiş):
  - `GetLines` — Tüm hatlar
  - `GetStationsByLineId` — Hat başına istasyonlar
  - `GetDirections` — Yön bilgisi
  - `GetTimeTable` — Sefer tarifeleri
  - `GetAnnouncements` — Anlık duyurular

**ÖNEMLİ KISITLAMA:** Metro İstanbul'un REST API'si canlı tren konumu vermiyor, sadece sefer tarifeleri. Bu yüzden trenleri **tarife-bazlı simülasyon** ile hareket ettiriyoruz (aşağıda 5.4'te açıklanıyor). Bu Mini Tokyo 3D'nin de yaptığı şey — birçok operatör canlı tren konumu yayınlamıyor.

**4.2.3. Marmaray ve Vapur Verileri**

- **Marmaray:** Sefer tarifeleri GTFS paketinde mevcut. Canlı konum verisi **yok**. Metro ile aynı tarife-bazlı simülasyon kullanılacak.
- **Şehir Hatları Vapurları:** GTFS paketinde mevcut. Canlı konum verisi **yok**. Tarife-bazlı simülasyon.

**4.2.4. Ek veri kaynağı: ulasav.csb.gov.tr**

Çevre, Şehircilik ve İklim Değişikliği Bakanlığı'nın "Türkiye Ulaşım Portalı" ([ulasav.csb.gov.tr](https://ulasav.csb.gov.tr/)) İETT Sefer Gerçekleşme servisini bir dataset olarak listeliyor. Bu ikincil kaynak — öncelik İBB'nin resmi API'si, ama İBB'de sorun yaşanırsa fallback olarak değerlendirilebilir. Rate limit dokümante değil, test edilmedi.

### 4.3. Veri Güncelleme Sıklığı

| Veri Türü | Güncelleme Sıklığı | Notlar |
|---|---|---|
| İETT canlı konumlar (sunucu) | **60 saniye** | Backend refresh rate'iyle (~60s) senkron |
| İETT canlı konumlar (istemci) | **Sürekli (60 FPS)** | Client-side interpolation ile akıcı render |
| Metro tarife simülasyonu | **Sürekli (client-side)** | `stop_times` + `shapes` ile interpolasyon |
| Marmaray simülasyonu | **Sürekli (client-side)** | Tarayıcı içinde interpolasyon |
| Vapur simülasyonu | **Sürekli (client-side)** | Tarayıcı içinde interpolasyon |
| Kapı no → hat eşlemesi | **Günde 1** | `GetIettArsivGorev_json` bir kez çağrılır |
| Statik GTFS | **Haftada 1** | Celery beat günlük kontrol, değişiklik varsa yeniden import |
| İETT duyuruları | **5 dakika** | `GetDuyurular_json` (ayrı endpoint) |
| Metro İstanbul duyuruları | **5 dakika** | `GetAnnouncements` |

**Rate limiting implementasyon detayları (ölçülmüş değerlere göre):**

- **Sliding window:** ~40 dakika, pencerede ~72 çağrı hakkı (ampirik olarak ölçüldü)
- **Hedefimiz:** 60 saniyede bir çağrı → saatte 60 çağrı, 40-dk pencerede 40 çağrı
- **Kullanım oranı:** Pencere kapasitesinin %56'sı (44 çağrı tampon)
- **Celery beat schedule:** `fetch_iett_fleet` her 60 saniyede bir
- **Redis sayaç:** Son 40 dakikadaki çağrı sayısı, 60'a ulaşırsa pause
- **Cooldown davranışı:** Rate limit ihlal edilirse ~30 dakika tamamen bloklu kalıyor — bu süre zarfında stale cache kullan, UI'da "Canlı veri gecikiyor" banner'ı göster
- **Distributed lock:** Prod'da birden fazla worker varsa sadece bir tanesi çağrı yapsın (Redis SETNX lock)
- **Stale cache TTL:** 5 dakika (normal) → 45 dakika (hata moduna geçilirse)
- **UI göstergesi:** "Son güncelleme: X saniye önce" — 90 saniyeyi geçerse sarı, 180 saniyeyi geçerse kırmızı

---

## 5. Mimari

### 5.1. Genel Mimari Şeması

```
┌─────────────────────────────────────────────────────────────────┐
│                    VERİ KAYNAKLARI (İBB)                         │
├──────────────────────┬──────────────────────┬──────────────────┤
│  İETT SOAP           │  Metro İstanbul REST │  GTFS statik     │
│  (canlı konum)       │  (tarife, istasyon)  │  (ZIP dosyaları) │
└──────────┬───────────┴──────────┬───────────┴────────┬─────────┘
           │                       │                    │
           ▼                       ▼                    ▼
┌─────────────────────────────────────────────────────────────────┐
│             ADAPTÖR KATMANI (Celery Workers)                     │
│  • SOAP→JSON dönüşümü (zeep)                                     │
│  • Normalize edilmiş "VehiclePosition" formatına çevirme         │
│  • Rate limiting, retry, cache                                   │
└──────────┬──────────────────────────────────────────┬───────────┘
           │                                           │
           ▼                                           ▼
┌──────────────────────────────┐    ┌───────────────────────────────┐
│  PostgreSQL + PostGIS        │    │  Redis                         │
│  • GTFS statik veri           │    │  • Canlı konum pub/sub         │
│  • Hatlar, duraklar, rotalar  │    │  • API response cache          │
│  • Kullanıcılar (v1.1+)       │    │  • Channel layer (Channels)    │
└──────────┬───────────────────┘    └──────────┬────────────────────┘
           │                                    │
           ▼                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                        DJANGO BACKEND                            │
├──────────────────────┬──────────────────────┬──────────────────┤
│  REST API            │  Django Channels     │  Admin Panel     │
│  (DRF)               │  (WebSocket)         │                  │
│  • /api/routes/      │  • /ws/vehicles/     │  • GTFS yönetim  │
│  • /api/stops/       │  • Canlı konum push  │  • Durak/hat CRUD │
│  • /api/trips/       │                      │  • Log görüntüleme│
└──────────┬───────────┴──────────┬───────────┴──────────────────┘
           │                       │
           │ HTTP (statik veri)    │ WebSocket (canlı veri)
           ▼                       ▼
┌─────────────────────────────────────────────────────────────────┐
│                      FRONTEND (Browser)                          │
├──────────────────────────────────────────────────────────────────┤
│  MapLibre GL JS (harita motoru, 3D binalar, terrain)            │
│  Three.js (araç 3D geometrileri)                                 │
│  deck.gl (büyük veri katmanları, hat çizgileri)                  │
│  Vanilla JS / TypeScript (uygulama mantığı)                      │
│  i18next (TR/EN çeviri)                                          │
└──────────────────────────────────────────────────────────────────┘
```

### 5.2. Teknoloji Seçimleri ve Gerekçeler

| Katman | Teknoloji | Gerekçe |
|---|---|---|
| Dil (backend) | Python 3.11+ | Django, zeep (SOAP), gtfs-kit kütüphaneleri için |
| Framework | Django 5.x | Geliştiricinin deneyimi, GeoDjango, admin paneli, DRF ekosistemi |
| API | Django REST Framework | Standart, stabil, dokümantasyon güzel |
| WebSocket | Django Channels 4.x | Django içinde kalmak, ayrı Node.js kurulmasın |
| ASGI server | Daphne (geliştirme), Uvicorn (production) | Channels uyumu |
| Veritabanı | PostgreSQL 16 + PostGIS 3.4 | Mekansal sorgular, GTFS ile doğal uyum |
| Cache / Pub-sub | Redis 7.x | Channels backend, Celery broker, response cache |
| Task queue | Celery 5.x + Redis broker | Periyodik SOAP çağrıları için |
| Periyodik görevler | django-celery-beat | Admin panelinden yönetilebilir zamanlayıcı |
| SOAP client | zeep | Python'da standart SOAP kütüphanesi |
| GTFS parsing | gtfs-kit | GTFS ZIP okuma, validasyon |
| Frontend dil | TypeScript | Tip güvenliği, agent'ın daha az hata yapması |
| Frontend build | Vite | Hızlı, modern, Django static ile uyumlu |
| Harita motoru | MapLibre GL JS 5.x | Açık kaynak Mapbox fork, 3D terrain desteği |
| 3D | Three.js (MapLibre custom layer ile) | Mini Tokyo 3D yaklaşımı |
| Veri görselleştirme | deck.gl | Binlerce araç render için GPU kullanır |
| Harita tile'ları | OpenFreeMap | Tamamen ücretsiz, API key yok |
| DEM / terrain | Mapterhorn | Ücretsiz raster-DEM |
| Test | pytest (backend), Vitest (frontend) | Modern, hızlı |
| Code quality | ruff, black, eslint, prettier | Opinionated, agent için iyi |

### 5.3. Ortak Veri Formatı: `VehiclePosition`

Farklı kaynaklardan gelen verileri tek bir forma normalize ediyoruz. Bu, GTFS-Realtime `VehiclePosition` mesajından esinleniyor ama daha basit:

```python
# backend/realtime/schemas.py
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class VehiclePosition(BaseModel):
    vehicle_id: str           # "C-231" (İETT kapı no) veya "M2-T-042"
    route_id: str             # "15B" veya "M2"
    trip_id: Optional[str]    # GTFS trip_id, eşleşirse
    latitude: float
    longitude: float
    bearing: Optional[float]  # Yön derecesi (0-360), hesaplanabilir
    speed: Optional[float]    # km/h, ölçülebilirse
    timestamp: datetime
    source: str               # "iett-soap", "simulated-metro", "simulated-ferry"
    mode: str                 # "bus", "metro", "marmaray", "tram", "funicular", "ferry"
```

**Frontend WebSocket mesaj formatı (JSON):**

```json
{
  "type": "vehicles_update",
  "timestamp": "2026-04-19T14:23:45Z",
  "vehicles": [
    {
      "id": "C-231",
      "route": "15B",
      "lat": 41.04885,
      "lon": 29.10322,
      "bearing": 87.5,
      "mode": "bus"
    }
  ]
}
```

### 5.4. Tarife-Bazlı Simülasyon (Metro, Marmaray, Vapur)

Canlı konum verisi olmayan modlar için **client-side simülasyon** yapıyoruz:

1. **Sunucu tarafı:** GTFS `stop_times.txt` veriyi yükler, her trip için durak-zaman çiftlerini veritabanına koyar.
2. **API:** `/api/trips/active/?mode=metro&time=now` — şu anda aktif olan tripleri ve durak geçiş zamanlarını döner.
3. **İstemci tarafı:** Her trip için, şu anki zamana göre durak A ile durak B arasında interpolasyon yapar:
   - `stop_times.txt`'den: durak A'dan 14:23:00'de çıktı, durak B'ye 14:25:30'da varıyor
   - `shapes.txt`'den: A ile B arası geometri (polyline)
   - Şu an 14:24:15 ise: yolun %50'sinde, bu konumu polyline üzerinde hesapla
4. **Animasyon:** `requestAnimationFrame` ile sürekli yeniden hesapla

Bu yaklaşım Mini Tokyo 3D'nin ana mekanizmasıdır. Canlı veri yokken bile "hareketli" hissi verir. Tabii gerçek gecikmeleri yansıtmaz, o yüzden UI'da bir "Simulated" badge gösterelim.

**Simülasyon için kritik veri:** `shapes.txt` hat geometrileri olmazsa simülasyon düz çizgiyle ilerler (çirkin görünür). İBB GTFS paketinde shapes varsa kullan, yoksa duraklar arası OSM'den yol çekmemiz gerekir (karmaşık, Faz 5'te ele al).

### 5.5. 3D Sahne Stratejisi

**Görsel Yaklaşım: Esnek mimari, A'dan başla B'ye geliş**

**İlk sürümde (v1.0):**
- **Base map:** OpenFreeMap "bright" veya "positron" stili
- **3D binalar:** MapLibre `fill-extrusion` layer'ı, OpenStreetMap'in `building` tag'inden gelen yükseklik/kat bilgisiyle
- **3D terrain:** Mapterhorn DEM ile, Boğaz kenarları, Çamlıca Tepesi, Pierre Loti, Galata bölgesi gibi topografyalar otomatik yükselir
- **Landmark'lar:** OSM'de ne tag varsa o render edilir. Ayasofya, Galata Kulesi gibi yapılar OSM'de detaylı mappe edilmişse kubbe/kule olarak görünür; değilse generic extrusion olarak görünür. Biz data-side iyileştirme yapmayız, render-side'da ne varsa gösteririz.
- **Su yüzeyleri:** Boğaz, Haliç, Marmara Denizi OSM'den otomatik alınır, özel mavi renklendirilir
- **Araçlar:** Three.js `BoxGeometry` ile basit kutular. Her mod için renk kodu:
  - Otobüs: İETT kırmızı (#E40521)
  - Metro hattı rengi (M1A sarı, M2 yeşil, M3 mavi, vb. — gerçek kurumsal renkler)
  - Marmaray: mavi-beyaz
  - Tramvay: İETT tramvay mavisi
  - Vapur: kırmızı-beyaz

**Sonraki sürümlerde (v1.4+):**
- Landmark 3D modelleri (manuel GeoJSON + `extrude` özel property'si ile)
- Araç geometrileri daha detaylı (otobüs silueti, metro vagonu)
- Gelişmiş terrain shader'ları

### 5.6. Geliştirme Ortamı

**Geliştirici makinesinde çalıştırma:**

Docker kullanmıyoruz (tercih üzere). Aşağıdaki servisler yerel olarak çalışır:

1. **PostgreSQL 16 + PostGIS** — yerel kurulum (Homebrew, apt, Windows installer)
2. **Redis 7** — yerel kurulum
3. **Django geliştirme sunucusu** — `python manage.py runserver 8000`
4. **Django Channels ASGI** — `daphne -p 8001 config.asgi:application`
5. **Celery worker** — `celery -A config worker -l INFO`
6. **Celery beat** — `celery -A config beat -l INFO`
7. **Frontend dev sunucusu** — `npm run dev` (Vite, port 5173)

**Port haritası:**

| Port | Servis | Notlar |
|---|---|---|
| 8000 | Django HTTP (runserver) | REST API, admin |
| 8001 | Daphne ASGI | WebSocket endpoint'i `/ws/` |
| 5173 | Vite dev server | Frontend |
| 5432 | PostgreSQL | Varsayılan |
| 6379 | Redis | Varsayılan |

> **⚠️ GELİŞTİRME ORTAMI KURULUM UYARISI (Antigravity agent dikkatine):**
> Bu proje yeni bir makine üzerinde kurulurken **yeni bir PostgreSQL veritabanı**
> (`mini_istanbul_dev`) oluşturulmalı ve yukarıdaki portların **kullanılabilir**
> olduğundan emin olunmalıdır. Port 8001 ve 5173 diğer projeler tarafından
> kullanılıyorsa `.env` dosyasında değiştirin. Kurulum adımlarının tamamı bu
> dokümanın 8. bölümünde (Kurulum Kılavuzu) listelenmiştir.

**Frontend proxy ayarı:** Vite dev server, `/api/*` ve `/ws/*` isteklerini Django'ya proxy'ler (CORS derdi yok):

```js
// frontend/vite.config.ts
server: {
  proxy: {
    '/api': 'http://localhost:8000',
    '/ws': { target: 'ws://localhost:8001', ws: true }
  }
}
```

---

## 6. Django Uygulama Yapısı

### 6.1. Proje Dizin Yapısı

```
mini-istanbul/
├── backend/
│   ├── config/                      # Django project settings
│   │   ├── __init__.py
│   │   ├── settings/
│   │   │   ├── base.py
│   │   │   ├── development.py
│   │   │   └── production.py
│   │   ├── urls.py
│   │   ├── asgi.py                  # Channels için
│   │   ├── wsgi.py
│   │   └── celery.py
│   │
│   ├── apps/
│   │   ├── gtfs/                    # Statik GTFS verileri
│   │   │   ├── models.py            # Agency, Route, Stop, Trip, StopTime, Shape
│   │   │   ├── admin.py
│   │   │   ├── serializers.py       # DRF
│   │   │   ├── views.py             # REST endpoints
│   │   │   ├── urls.py
│   │   │   └── management/
│   │   │       └── commands/
│   │   │           ├── import_gtfs.py    # GTFS ZIP → DB
│   │   │           └── download_gtfs.py  # İBB'den indir
│   │   │
│   │   ├── realtime/                # Canlı veri
│   │   │   ├── schemas.py           # Pydantic VehiclePosition
│   │   │   ├── adapters/
│   │   │   │   ├── iett_soap.py     # İETT SOAP wrapper
│   │   │   │   ├── metro_rest.py    # Metro İstanbul REST wrapper
│   │   │   │   └── base.py          # Ortak interface
│   │   │   ├── tasks.py             # Celery tasks
│   │   │   ├── consumers.py         # Channels WebSocket consumer
│   │   │   ├── routing.py           # WebSocket URL routing
│   │   │   └── publishers.py        # Redis pub/sub
│   │   │
│   │   └── core/                    # Ortak yardımcılar
│   │       ├── models.py            # Ortak abstract modeller
│   │       └── utils.py
│   │
│   ├── static/                      # Django static (admin vb.)
│   ├── templates/
│   ├── manage.py
│   ├── pyproject.toml               # Poetry ya da pip-tools
│   └── .env.example
│
├── frontend/
│   ├── src/
│   │   ├── main.ts                  # Giriş noktası
│   │   ├── map/
│   │   │   ├── MapController.ts     # MapLibre instance yönetimi
│   │   │   ├── layers/
│   │   │   │   ├── buildings3d.ts
│   │   │   │   ├── terrain.ts
│   │   │   │   ├── routes.ts        # Hat çizgileri (deck.gl)
│   │   │   │   └── vehicles.ts      # Three.js custom layer
│   │   │   └── styles/
│   │   │       └── istanbul-base.json
│   │   ├── data/
│   │   │   ├── api.ts               # REST API client
│   │   │   └── websocket.ts         # WebSocket client
│   │   ├── simulation/
│   │   │   └── interpolator.ts      # Tarife-bazlı simülasyon
│   │   ├── ui/
│   │   │   ├── StopPopup.ts
│   │   │   ├── RoutePanel.ts
│   │   │   └── LanguageSwitcher.ts
│   │   ├── i18n/
│   │   │   ├── tr.json
│   │   │   └── en.json
│   │   └── types/
│   │       └── index.ts             # Paylaşılan tipler
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts
│   └── tsconfig.json
│
├── docs/
│   ├── SETUP.md
│   ├── API.md
│   └── CONTRIBUTING.md
│
├── scripts/
│   └── initial-setup.sh             # DB oluştur, migrate, seed
│
├── .gitignore
├── README.md
└── LICENSE
```

### 6.2. Temel Django Modelleri (Özet)

Ayrıntılar için `docs/MODELS.md` (ayrıca yazılacak). Burada şema düzeyinde özet:

```python
# apps/gtfs/models.py (özet - tam hali farklı dosyada)

from django.contrib.gis.db import models

class Agency(models.Model):
    agency_id = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=200)
    url = models.URLField()
    timezone = models.CharField(max_length=50, default='Europe/Istanbul')
    lang = models.CharField(max_length=10, default='tr')

class Route(models.Model):
    ROUTE_TYPES = [
        (0, 'Tram'), (1, 'Subway'), (2, 'Rail'),
        (3, 'Bus'), (4, 'Ferry'), (6, 'Aerial'), (7, 'Funicular'),
    ]
    route_id = models.CharField(max_length=50, unique=True)
    agency = models.ForeignKey(Agency, on_delete=models.CASCADE)
    short_name = models.CharField(max_length=50)  # "M2", "15B"
    long_name = models.CharField(max_length=200)  # "Yenikapı - Hacıosman"
    route_type = models.IntegerField(choices=ROUTE_TYPES)
    color = models.CharField(max_length=7, default='#000000')  # #RRGGBB
    text_color = models.CharField(max_length=7, default='#FFFFFF')

class Stop(models.Model):
    stop_id = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=200)
    location = models.PointField(srid=4326)  # PostGIS
    location_type = models.IntegerField(default=0)  # 0=stop, 1=station, 2=entrance

class Shape(models.Model):
    """Hat geometrisi (simülasyon için kritik)"""
    shape_id = models.CharField(max_length=50, unique=True)
    geometry = models.LineStringField(srid=4326)

class Trip(models.Model):
    trip_id = models.CharField(max_length=100, unique=True)
    route = models.ForeignKey(Route, on_delete=models.CASCADE)
    shape = models.ForeignKey(Shape, null=True, on_delete=models.SET_NULL)
    headsign = models.CharField(max_length=200)
    direction_id = models.IntegerField(default=0)
    service_id = models.CharField(max_length=50)  # calendar.txt referansı

class StopTime(models.Model):
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name='stop_times')
    stop = models.ForeignKey(Stop, on_delete=models.CASCADE)
    arrival_time = models.DurationField()   # GTFS: HH:MM:SS, >24 olabilir
    departure_time = models.DurationField()
    stop_sequence = models.IntegerField()

    class Meta:
        ordering = ['trip', 'stop_sequence']
        indexes = [models.Index(fields=['trip', 'stop_sequence'])]
```

### 6.3. REST API Endpoint'leri

```
GET  /api/agencies/                   Tüm operatörler
GET  /api/routes/                     Tüm hatlar (pagination)
GET  /api/routes/?mode=bus            Filtreleme
GET  /api/routes/{route_id}/          Tek hat detayı (geometri dahil)
GET  /api/routes/{route_id}/stops/    Hatın durakları (sıralı)
GET  /api/routes/{route_id}/shape/    Hatın geometrisi (GeoJSON LineString)

GET  /api/stops/                      Tüm duraklar (pagination + bbox filtre)
GET  /api/stops/?bbox=28.9,41.0,29.1,41.1  Bbox içindeki duraklar
GET  /api/stops/{stop_id}/            Tek durak detayı
GET  /api/stops/{stop_id}/upcoming/   Yaklaşan araçlar (next N arrivals)

GET  /api/trips/active/               Şu an aktif tripler
GET  /api/trips/active/?mode=metro    Mod filtresi
GET  /api/trips/{trip_id}/            Trip detayı (stop_times dahil)

GET  /api/vehicles/live/              Son bilinen canlı araç konumları (snapshot)
                                      (WebSocket yoksa fallback)

WS   /ws/vehicles/                    Canlı araç konumları (WebSocket)
                                      Mesaj: subscribe, unsubscribe
                                      Abone ol: { "action": "subscribe", "bbox": [...], "modes": [...] }
```

### 6.4. WebSocket Protokolü

**Bağlantı:** `ws://localhost:8001/ws/vehicles/`

**Client → Server mesajları:**

```json
// Sadece belirli bbox ve modlar için abone ol (performans için)
{
  "action": "subscribe",
  "bbox": [28.9, 40.9, 29.2, 41.2],
  "modes": ["bus", "metro", "ferry"]
}

// Abonelikten çık
{
  "action": "unsubscribe"
}
```

**Server → Client mesajları:**

```json
// Periyodik güncelleme (3-5 saniyede bir)
{
  "type": "vehicles_update",
  "timestamp": "2026-04-19T14:23:45Z",
  "vehicles": [
    {
      "id": "C-231",
      "route": "15B",
      "lat": 41.04885,
      "lon": 29.10322,
      "bearing": 87.5,
      "mode": "bus"
    }
    // ... diğer araçlar
  ]
}

// Hata
{
  "type": "error",
  "code": "INVALID_BBOX",
  "message": "bbox must be [west, south, east, north]"
}
```

---

## 7. Geliştirme Fazları (Iteration Plan)

Her faz **çalışır bir uygulama** çıkarır. Antigravity agent her faz sonunda durum kontrolü yapabilir.

### Faz 1: Veri Altyapısı (tahmini 2-3 hafta, tek kişi)

**Hedef:** Statik GTFS verisi PostGIS'te, admin panelinden görüntülenebilir, basit Leaflet haritada duraklar ve hatlar gösteriliyor.

**Çıktılar:**
- [x] Django projesi kurulmuş, PostgreSQL + PostGIS bağlı
- [x] `apps/gtfs/models.py` tamamlanmış, migrate edilmiş
- [x] `python manage.py download_gtfs` — İBB'den ZIP'leri indirir
- [x] `python manage.py import_gtfs` — ZIP → DB
- [x] Django admin'de Routes, Stops, Trips listelenebiliyor
- [x] `/api/routes/`, `/api/stops/` basit endpoint'leri çalışıyor
- [x] Basit bir Leaflet sayfası tüm durakları ve hatları gösteriyor (3D değil, sadece veri doğrulama için)

**Bitiş kriteri:** Haritaya baktığında İstanbul'un tüm durak ve hatları görünüyor; veri tutarlı.

### Faz 2: Canlı Veri Adaptörü (2-3 hafta)

**Hedef:** İETT SOAP servisinden canlı otobüs konumları alınıyor (60 saniyede bir), Redis'e yayınlanıyor, admin panelinden sayı takip edilebiliyor.

**Çıktılar:**
- [ ] `apps/realtime/adapters/iett_soap.py` — ham HTTP ile SOAP client (zeep kullanma, WSDL parse sorunu var)
  - `GetFiloAracKonum_json()` çağrısı (tüm filo, tek çağrı, ~1.1MB response)
  - `GetIettArsivGorev_json(Tarih)` günlük çağrısı (kapı no → hat eşlemesi)
- [ ] Kapı no → hat mapping Redis'te günlük cache'leniyor
- [ ] `apps/realtime/tasks.py` — Celery periyodik görevi **her 60 saniyede** (backend refresh rate'iyle senkron)
- [ ] Redis pub/sub ile konumlar `vehicles:iett` kanalına yayınlanıyor
- [ ] **Rate limit koruması (kritik):**
  - Redis sliding window sayacı (40 dakika, 60 çağrı soft limit, 72 hard limit)
  - 500 hata durumunda 30 dakika pause
  - Distributed lock (Redis SETNX) — sadece bir worker instance çağrı yapsın
- [ ] Admin panelinde "Live Vehicles" sayfası:
  - Son 60 saniyedeki araç sayısı
  - Son çağrının timestamp'i
  - Son 40 dakikadaki çağrı sayısı (grafikle)
  - API health durumu (green/yellow/red)
  - Rate limit durumu ("44 çağrı / 40dk | 28 hak kaldı")
- [ ] Unit testler: `test_iett_soap_parser.py`, `test_rate_limiter.py`, `test_stale_cache.py`
- [ ] Stale data fallback: son başarılı veriyi 5 dk cache'te tut, hata durumunda 45 dk

**Bitiş kriteri:** `celery -A config worker` + `beat` çalışırken, 60 saniye boyunca bekleyince Redis CLI'dan `SUBSCRIBE vehicles:iett` dinleyince ~6900 aracın konumu akıyor. Admin panelinde 40-dk pencere kullanım oranı %56 civarında (40/72 çağrı).

### Faz 3: WebSocket Katmanı (1-2 hafta)

**Hedef:** Frontend bir sayfa açıp canlı noktaları Leaflet haritada hareketli görüyor.

**Çıktılar:**
- [ ] Django Channels kuruldu, Daphne port 8001'de
- [ ] `apps/realtime/consumers.py` — `VehiclePositionConsumer`
- [ ] Client subscribe/unsubscribe mantığı (bbox + modes filtresi)
- [ ] Redis pub/sub → WebSocket push bridge
- [ ] Basit frontend test sayfası: Leaflet + ws bağlantısı, hareket eden noktalar

**Bitiş kriteri:** `python manage.py runserver` + `daphne` + `celery` aynı anda çalışırken tarayıcıda noktalar gerçekten hareket ediyor.

### Faz 4: 3D Frontend (3-4 hafta)

**Hedef:** MapLibre + Three.js ile 3D harita, araçlar kutu olarak görünüyor ve **akıcı** hareket ediyor (60sn aralıklı verinin üstüne interpolasyon).

**Çıktılar:**
- [ ] Vite + TypeScript frontend kuruldu
- [ ] MapLibre GL JS ile OpenFreeMap stil yüklendi
- [ ] 3D binalar (`fill-extrusion`) aktif
- [ ] Mapterhorn terrain aktif
- [ ] Three.js custom layer yazıldı (araçlar için)
- [ ] WebSocket → vehicle state → 3D mesh update pipeline
- [ ] **Client-side interpolation (zorunlu, zira veri 60sn aralıklı):**
  - `apps/frontend/src/simulation/bus_interpolator.ts`
  - T₀ (önceki) ve T₁ (yeni) konumlar arasında yol-bilinçli interpolasyon
  - Araç hat bilgisi (kapı no → hat eşlemesinden) `shapes.txt` polyline'a map edilir
  - Polyline üzerinde aracı "en yakın nokta"ya projekte et
  - İki snapshot arasında polyline boyunca lineer ilerleme
  - 60 FPS `requestAnimationFrame` döngüsü
  - **Edge case'ler:** Araç polyline'dan sapmışsa (GPS hatası, rota değişikliği) fallback — iki konum arasında düz çizgi
- [ ] Kamera kontrolleri (pitch, bearing, zoom)
- [ ] Durak tıklama → popup
- [ ] Hat tıklama → hat highlight
- [ ] "Son güncelleme: X saniye önce" UI göstergesi

**Bitiş kriteri:** `npm run dev` + backend çalışırken `localhost:5173`'te İstanbul'un 3D haritası geliyor ve otobüsler akıcı (60 FPS, sanki sürekli veri geliyormuş gibi) hareket ediyor. 60 saniyede bir snapshot değişiyor ama kullanıcı bunu hissedemeyecek.

### Faz 5: Metro / Marmaray / Vapur Simülasyonu (2 hafta)

**Hedef:** Otobüs dışındaki modlar da hareketli.

**Çıktılar:**
- [ ] `/api/trips/active/` endpoint'i yazıldı
- [ ] Client-side `interpolator.ts` — `stop_times` + `shape` → konum
- [ ] Requestanimationframe loop ile sürekli güncelleme
- [ ] UI'da "Simulated" badge (canlı verisi olmayan araçlar için)
- [ ] Tüm modlar için farklı renkli geometri

**Bitiş kriteri:** Metro, Marmaray ve vapur araçları da haritada hareketli.

### Faz 6: Cilalama (süresiz, kontinü)

**Hedef:** Kullanıcı deneyimi, performans, i18n, mobil uyum.

**Çıktılar:**
- [ ] Türkçe / İngilizce dil değiştirici (i18next)
- [ ] Responsive tasarım (mobil breakpoint)
- [ ] Performans: görünür bbox dışındaki araçları gizle
- [ ] Durak arama (autocomplete)
- [ ] Hat filtreleme paneli
- [ ] Saat çubuğu (v2'ye ertelenebilir)
- [ ] Landmark özel GeoJSON (Ayasofya, Galata vb. — opsiyonel)
- [ ] Production deployment dokümanı

---

## 8. Kurulum Kılavuzu (Antigravity Agent için)

### 8.1. Ön Koşullar

Geliştirme makinesinde aşağıdakiler kurulu olmalı:

- **Python 3.11 veya üzeri** (`python3 --version` ile kontrol)
- **Node.js 20 LTS veya üzeri** (`node --version` ile kontrol)
- **PostgreSQL 16** (PostGIS eklentisi ile)
- **Redis 7.x**
- **Git**

Kurulu değilse (işletim sistemine göre):

```bash
# macOS (Homebrew)
brew install python@3.11 node@20 postgresql@16 redis
brew services start postgresql@16
brew services start redis

# Ubuntu / Debian
sudo apt update
sudo apt install python3.11 python3.11-venv python3-pip nodejs npm \
    postgresql-16 postgresql-16-postgis-3 redis-server

# Windows
# PostgreSQL: https://www.postgresql.org/download/windows/  (PostGIS Stack Builder ile)
# Redis: Microsoft Store'dan "Redis for Windows" ya da WSL içinde
# Python ve Node: python.org ve nodejs.org'dan
```

### 8.2. Veritabanı Kurulumu

> **⚠️ ÖNEMLİ: Yeni bir veritabanı oluşturuyoruz.**
> Bu projenin kendi izole veritabanı olmalı. Başka projelerin db'sini paylaşmıyoruz.

```bash
# PostgreSQL'e bağlan
sudo -u postgres psql   # Linux
psql postgres           # macOS Homebrew

-- Aşağıdakileri psql içinde çalıştır:
CREATE USER mini_istanbul WITH PASSWORD 'change_me_in_env';
CREATE DATABASE mini_istanbul_dev OWNER mini_istanbul;
\c mini_istanbul_dev
CREATE EXTENSION postgis;
CREATE EXTENSION postgis_topology;
\q
```

### 8.3. Proje Kurulumu

```bash
# 1. Repo'yu klonla
git clone https://github.com/yagizfirat/mini-istanbul-3d.git
cd mini-istanbul-3d

# 2. Backend virtualenv
cd backend
python3.11 -m venv venv
source venv/bin/activate        # Linux/macOS
# venv\Scripts\activate         # Windows PowerShell

pip install --upgrade pip
pip install -r requirements/development.txt

# 3. Environment dosyası
cp .env.example .env
# .env içinde şunları güncelle:
#   DATABASE_URL=postgres://mini_istanbul:change_me_in_env@localhost:5432/mini_istanbul_dev
#   REDIS_URL=redis://localhost:6379/0
#   SECRET_KEY=<yeni bir secret key, python -c "import secrets; print(secrets.token_urlsafe(50))">
#   DEBUG=True
#   ALLOWED_HOSTS=localhost,127.0.0.1

# 4. Migrate
python manage.py migrate

# 5. Superuser
python manage.py createsuperuser

# 6. GTFS verisini indir ve import et (15-30 dakika sürebilir)
python manage.py download_gtfs
python manage.py import_gtfs

# 7. Frontend bağımlılıkları
cd ../frontend
npm install
```

### 8.4. Çalıştırma

Beş ayrı terminal penceresi gerekiyor (ya da `tmux`, `screen`, vs.):

```bash
# Terminal 1: Django REST API
cd backend
source venv/bin/activate
python manage.py runserver 8000

# Terminal 2: Daphne WebSocket server
cd backend
source venv/bin/activate
daphne -p 8001 config.asgi:application

# Terminal 3: Celery worker (canlı veri adaptörü)
cd backend
source venv/bin/activate
celery -A config worker -l INFO

# Terminal 4: Celery beat (periyodik görevler)
cd backend
source venv/bin/activate
celery -A config beat -l INFO

# Terminal 5: Frontend dev server
cd frontend
npm run dev
```

Tarayıcıda `http://localhost:5173` adresine git.

### 8.5. Çalışma Sonrası Doğrulama

Her şey çalışıyorsa şunları görmelisin:

1. `http://localhost:5173` — İstanbul'un 3D haritası yükleniyor (Faz 4'ten sonra)
2. `http://localhost:8000/admin/` — Django admin, Routes/Stops listelenebiliyor
3. `http://localhost:8000/api/routes/` — JSON olarak hat listesi dönüyor
4. WebSocket: Chrome DevTools → Network → WS sekmesi → `ws://localhost:8001/ws/vehicles/` bağlantısı 101 Switching Protocols ile kurulmuş
5. Terminal 3 (Celery worker) loglarında: `Fetched X vehicles from IETT SOAP` mesajları

---

## 9. Test Stratejisi

### Backend
- **Unit testler (pytest):** Her model, her serializer, her adapter
- **Integration testler:** API endpoint'leri, WebSocket consumer'ları
- **Mock external APIs:** İETT SOAP ve Metro REST çağrıları `responses` ya da `vcr.py` ile kaydedilip replay edilir (canlı API'ye test sırasında gitmeyiz)

### Frontend
- **Unit testler (Vitest):** Interpolator, API client, WebSocket client
- **E2E:** Playwright (gelecek fazda — MVP'de opsiyonel)

### Hedef kapsama
- Backend: >80% line coverage
- Frontend: >60% line coverage (3D render tarafı zor)

---

## 10. Risk Analizi

| Risk | Etki | Azaltma Stratejisi |
|---|---|---|
| İETT rate limit (40dk/72 çağrı) aşılırsa | **Kritik** | 60sn aralıklı çağrı + Redis sliding window sayacı + distributed lock; 500 hata alınırsa 30 dakika pause |
| İETT SOAP servisi çökerse | Yüksek | Redis'te son bilinen konumu cache'le (TTL 45dk hata modunda), UI'da "Veri gecikmesi" uyarısı |
| SOAP endpoint'i değişirse / kapanırsa | Yüksek | Adaptör katmanı yüzünden sadece bir dosya değişir; fallback olarak ulasav.csb.gov.tr |
| Kapı no → hat eşlemesi bozulursa | Orta | Araç "unknown route" ile gösterilir, hata log'lanır, günlük re-fetch |
| GTFS formatı İBB'de güncellenirse | Orta | `gtfs-kit` validator + her import'ta log, şema değişikliklerini yakala |
| GTFS'te `shapes.txt` eksikse (hat için) | Orta | Duraklar arası düz çizgi fallback + Faz 6'da OSM'den route shape çekme |
| Performans: 6900+ araç aynı anda | Yüksek | Bbox filtresiyle sadece görünür araçlar, deck.gl GPU kullanımı, Three.js instancing |
| Client-side interpolation yanlış tahmin yapar | Düşük | Araç yol dışına çıkarsa 60sn sonraki veri düzeltir; UI'da "tahmini konum" badge (opsiyonel) |
| OSM'de bina verisi eksikse | Düşük | Generic extrusion yine gösterilir, Faz 6'da community mapping katkısı |
| Tarih/saat/zone bug'ları | Orta | Her şey UTC + Europe/Istanbul; Django TIME_ZONE = 'Europe/Istanbul', USE_TZ=True |
| Aşırı WebSocket bağlantısı (DOS benzeri) | Düşük | Rate limit per IP, anonymous için connection cap |
| İBB rate limit politikası değişirse | Orta | Ampirik testler periyodik tekrarlansın (3-6 ayda bir), strateji güncellensin |

---

## 11. Açık Sorular (Geliştirme Sırasında Karar Verilecek)

**Cevaplanan sorular (v0.1 ve v0.2'den):**
- ~~İETT SOAP endpoint URL'si nedir?~~ → **Cevaplandı:** `api.ibb.gov.tr/iett/FiloDurum/SeferGerceklesme.asmx`, WSDL bozuk ama ham SOAP çalışıyor
- ~~Rate limit var mı, ne kadar?~~ → **Cevaplandı:** 40 dakikalık sliding window, ~72 çağrı
- ~~API key gerekiyor mu?~~ → **Cevaplandı:** Gerekmiyor, anonim erişim açık
- ~~Backend refresh rate?~~ → **Cevaplandı:** Ortalama 60.3 saniye

**Geliştirme sırasında cevaplanacak:**

1. `GetFiloAracKonum_json()` dönen veride bazı araçların `Operator` değeri `OHO` olarak geliyor (Akyolbil dış operatörleri). Bunlar İETT hatları değil, özel halk otobüsleri olabilir. Nasıl sınıflandırılacaklar? (Faz 2'de data eksplorasyonu ile)
2. GTFS paketindeki `shapes.txt` tüm hatlar için mevcut mu, yoksa bazı hatlar için geometri eksik mi? (Faz 1'de test edilecek)
3. Metro İstanbul REST API'si authentication gerektiriyor mu? Rate limit var mı? Ayrı mı İETT SOAP ile paylaşımlı mı? (Faz 1-2 arası test edilecek — **önemli:** İETT test scripti Metro İstanbul API için de uyarlanıp çalıştırılmalı)
4. Marmaray ve İDO GTFS paketleri ayrı mı yoksa "Genel Toplu Ulaşım GTFS" içinde birleşik mi? (Faz 1'de keşfedilecek)
5. `GetIettArsivGorev_json(Tarih)` bugünkü tarih için çalışıyor mu yoksa sadece geçmiş için mi? (Faz 2'de test edilecek — kapı no → hat eşlemesinin temelini oluşturuyor)
6. İETT'nin "güzergah kodu" kavramı GTFS'teki `shape_id` veya `direction_id`'ye nasıl eşleşiyor? (Faz 1'de veri incelemesi)
7. Diğer İETT SOAP servisleri (Duyurular, PlanlananSeferSaati, vb.) SeferGerceklesme ile rate limit paylaşımlı mı, bağımsız mı? Test et.
8. Landmark 3D modellerini hangi lisansla nereden alacağız? (Faz 6'da kararlaştırılır — Sketchfab CC0, manuel GeoJSON, Blender modeling)

---

## 12. Lisanslama

- **Kod lisansı:** MIT
- **Veri lisansı:**
  - İBB açık veri: İstanbul Büyükşehir Belediyesi Açık Veri Lisansı (attribution gerekli)
  - OpenStreetMap: ODbL (attribution gerekli, türev eserler ODbL olmalı)
  - OpenFreeMap: Attribution gerekli (MapLibre otomatik ekliyor)
  - Mapterhorn DEM: Attribution gerekli
- **Attribution metni (uygulamada görünecek):**
  > Veri: © İstanbul Büyükşehir Belediyesi, © OpenStreetMap katkıda bulunanlar
  > Harita: © OpenFreeMap © OpenMapTiles
  > Arazi: © Mapterhorn

---

## 13. Referanslar

**Ana referanslar:**
- **İETT Web Servis Kullanım Dokümanı v1.5 (İBB resmi PDF):** [pdf link](https://data.ibb.gov.tr/dataset/3e32bb5d-2936-41eb-bdc7-65b843487e99/resource/6821f452-f6ff-49e9-940a-d4ebfc78f03e/download/iett-web-servis-kullanm-dokumanv.1.2.pdf) — **KESİN KAYNAK, İETT API için primary reference**
- **Mini Tokyo 3D:** https://github.com/nagix/mini-tokyo-3d (mimari ilham kaynağı)
- **Mini Tokyo 3D live:** https://minitokyo3d.com/
- **İBB Açık Veri Portalı:** https://data.ibb.gov.tr/

**Standartlar:**
- **GTFS spec:** https://gtfs.org/schedule/reference/
- **GTFS-Realtime spec:** https://gtfs.org/realtime/reference/

**Teknoloji dokümantasyonu:**
- **MapLibre GL JS:** https://maplibre.org/maplibre-gl-js/docs/
- **OpenFreeMap:** https://openfreemap.org/
- **Django Channels:** https://channels.readthedocs.io/
- **Celery periodic tasks:** https://docs.celeryproject.org/en/stable/userguide/periodic-tasks.html

**Veri kümeleri:**
- **İETT GTFS veri seti:** https://data.ibb.gov.tr/dataset/iett-gtfs-verisi
- **Genel Toplu Ulaşım GTFS:** https://data.ibb.gov.tr/dataset/public-transport-gtfs-data

**Community projeleri (referans, dependency değil):**
- **hakanatak/dataibbgovtr_python:** https://github.com/hakanatak/dataibbgovtr_python
- **İETT SOAP kullanım örneği:** https://burakbayramli.github.io/dersblog/sk/2023/01/iett-ibb-otobus-verisi.html
- **AydinAdn/IBB.Api (.NET):** https://github.com/AydinAdn/IBB.Api

**Proje ampirik testleri (v0.3 için yapıldı):**
- `test_ibb_token_v2.py` — Token uyumluluğu testi
- `test_rate_limit.py` — Rate limit dayanıklılık testi (fast/long modes)
- `test_29b_tracking.py` — Araç hareket takibi + cooldown testi
- `test_refresh_rate.py` — Backend refresh rate ölçümü

---

## 14. Doküman Versiyon Geçmişi

| Versiyon | Tarih | Değişiklik |
|---|---|---|
| 0.1 | 2026-04-19 | İlk taslak |
| 0.2 | 2026-04-19 | İETT resmi web servis dokümanı incelendi, rate limit keşfedildi (PDF'te "saatte 100" yazıyor), 3 strateji seçeneği eklendi |
| 0.3 | 2026-04-19 | Ampirik testler yapıldı: rate limit'in ~40dk/72 çağrı sliding window olduğu ölçüldü, backend refresh rate'in 60s olduğu doğrulandı, token'ın SOAP'ta etkisiz olduğu gösterildi. 3 seçenek kaldırıldı, **60 saniye aralıklı çağrı + client-side interpolation** kesinleştirildi |
