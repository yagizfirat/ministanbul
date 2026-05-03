# İstanbul ulaşım canlı veri kaynağı araştırması

**Tarih:** 2026-05-03
**Amaç:** İETT bus mapping problemine alternatif canlı kaynak var mı? Üç gündür süren keşif zincirinin son turu — bu turdan sonra karar verilip kod turu açılacak.
**Kapsam:** Sadece public web bilgisi. Kod yazılmadı, SOAP/HTTP çağrı yapılmadı, reverse engineering denenmedi.

**Önceki turlar özeti:**
- Mevcut SOAP arşivi (`GetIettArsivGorev_json`) yapısal olarak stale.
- 29B koridorunda 62 vehicle, 0'ı 29B'ye mapped (β senaryo, mapping coverage zayıf).
- `GetHatOtoKonum_json` kesin kapalı (HTTP 500 NullReferenceException).
- Drift filter ters etki yapmıyor.

---

## Soru 1 — Resmi İETT/İBB canlı API var mı?

**Bulgu:** Mevcut SOAP servisi dışında YOK. Bizim halen kullandığımız `api.ibb.gov.tr/iett/...asmx` endpoint'leri tek seçenek; yeni public REST/GraphQL/streaming API yok.

**Detay:**
- `developer.ibb.gov.tr` → ECONNREFUSED (yayında değil).
- `api.ibb.gov.tr` (root) → HTTP 500 (dökümantasyon yok, sadece servis endpoint'leri).
- CKAN'da listelenen "API" formatlı 7 İETT web servisi — hepsi aynı SOAP namespace'i altında, son güncellemeleri 2024-11 / 2024-12. Yeni eklenen RT/REST yok.
- "IBB API key kayıt" araması: API anahtarı `data.ibb.gov.tr` kullanıcı paneli üzerinden veriliyor; SOAP servislerinin tabi olduğu rate limit'ler ampirik (40 dk pencere / 72 çağrı) — değişmemiş.
- `burakbayramli/dersblog` (2023) ve `AydinAdn/IBB.Api` (.NET, son commit 2023-03) aynı iki SOAP endpoint'ini wrap ediyor: `HatDurakGuzergah.asmx` + `SeferGerceklesme.asmx`. **Hiçbir 3. endpoint keşfedilmemiş.**

## Soru 2 — GTFS-Realtime İstanbul feed'i var mı?

**Bulgu:** YOK. **Bu turun en kritik kanıtı:** 2 hafta önce bir yazılım mühendisliği öğrencisi `data.ibb.gov.tr/datarequest`'te birebir bu soruyu sormuş ve talebi **"IETT Journey Web Service" (mevcut SOAP) gösterilerek kapatılmış**.

**Detay:**
- Kapatılan veri talebi: [`/datarequest/33ebac3e-e266-4bc2-8896-68d60ba0a15c`](https://data.ibb.gov.tr/datarequest/33ebac3e-e266-4bc2-8896-68d60ba0a15c) — "İETT GTFS-Realtime (RT) Veri Erişimi". Talep metni: statik veri için API anahtarı ile erişim sağlanıyor, GTFS-RT için "Policy Falsified" hatası alıyor, **API anahtarı üzerinden RT akış erişimi açılması talep ediliyor**. Cevap: "IETT Journey Web Service" (yani SOAP). Yani İBB resmen "GTFS-RT yayınlama planımız yok, mevcut SOAP'u kullan" demiş.
- Hâlâ açık olan kardeş talep: [`/datarequest/b22d4cac-07ea-4317-82cb-2501d6c61a6d`](https://data.ibb.gov.tr/datarequest/b22d4cac-07ea-4317-82cb-2501d6c61a6d) — "GTFS Veri Seti Kapsamının ve Anlık Sefer Verilerinin Güncellenmesi", 2 ay önce açıldı, statik GTFS'te eksik raylı hatlar (M3/M4/M5/M9/T5/F4) için. **2 ay boyunca İBB cevabı yok.** Static feed bile düzenli güncellenmiyor.
- Genel arama (`"GTFS-Realtime" Istanbul IETT vehicle_positions`) İstanbul'a özgü tek bir protobuf URL'i döndürmedi.

## Soru 3 — 3rd-party agregator'larda kayıt var mı?

**Bulgu:** YOK. transit.land Türkiye operatörleri sadece **İzmir**: Eshot, IZBAN, TRAM İZMİR. Üçü de yalnızca **statik GTFS**. İstanbul/İETT/İBB için tek bir feed kaydı yok.

**Detay:**
- `transit.land/operators?adm0_name=Turkey` → 3 operatör, hepsi İzmir.
- TRAM İZMİR feed'i (`f-izmir~tram`): GTFS static, kaynağı `tramizmir.com/gtfs/rail-tramizmir-gtfs.zip`, 2026-05-03 09:??'de fetch edildi. **GTFS-RT yok.**
- MobilityDatabase (`mobilitydatabase.org`, `api.mobilitydatabase.org`) Türkiye sorgusu: arama UI'sı JS ağırlıklı, redirect zinciri auth gerektiriyor. Ancak MobilityDB ile transit.land arasındaki yüksek federasyon nedeniyle transit.land'de yoksa MobilityDB'de de kayıtlı olma ihtimali çok düşük.
- Google Transit Partners / Citymapper / Moovit feed kaydı public API üzerinden listelenmiyor; muhtemelen İBB ile bilateral anlaşma var ama **public erişime kapalı**.

## İkincil bulgular

### CKAN'da yeni dataset (Faz 1'den bu yana)

- **IETT GTFS Data** — son güncelleme **2026-04-21** (ay içinde refresh edildi, hâlâ static, RT değil).
- **İETT Elektrikli Araç Özellikleri Verisi** — 2026-03-19 (XLSX, mapping ile alakasız).
- **İETT Otobüs Durakları / Hat Güzergahları (GeoJSON)** — 2026-03-18 (statik snapshot, mapping kullanımı için zaten Faz 1'de değerlendirildi).
- Web servisi datasetleri (Sefer Gerçekleşme, Planlanan Sefer Saati, Yolculuk vb.) — 2024-11/12'den beri güncellenmedi. **Bizim kullandığımız SOAP'lar bunlar; arşivin bayatlığı bizim ölçtüğümüz "stale" davranışıyla tutarlı.**

### Developer portal

- `developer.ibb.gov.tr` ve `iett.istanbul/api` benzeri portal **yayında değil**. İBB sadece `data.ibb.gov.tr` üzerinden API access veriyor, formatı SOAP olarak kalmış.

### Topluluk projeleri (GitHub `iett` topic)

| Repo | Son güncelleme | Yorum |
|---|---|---|
| `Rednexie/iettnext` | 2026-01-22 | **İBB tarafından idari baskıyla geçici kapatıldı.** README: "iettnext has been temporarily shut down due to administrative pressure and data access restrictions imposed by the Istanbul Metropolitan Municipality (İBB)." Aynı zamanda "Istanbul Electricity, Tramway and Tunnel Authority (IETT) for open(!) data" — ünlem işareti ironik. v2 için yaz aylarında görüşme planlıyorlar. **Bu bizim için kuvvetli bir uyarı sinyali.** |
| `AydinAdn/IBB.Api` | 2023-03-13 | .NET wrapper, SOAP, `GetVehicleLocationsAsync` + `VehicleLocationCacheService` (60s polling). Aynı endpoint, aynı kısıtlar. |
| `hakanatak/dataibbgovtr` | (Faz 1'den beri görüldü) | SOAP → GeoJSON proxy (`/api/filo`, `/api/durak`). README: "SOAP servisleri her gece 00:15'den sonra kapatılmaktadır." Bizimkiyle aynı backend, aynı bayatlık. |
| `deniz-blue/istanbus` | 2024-08-29 | **Arşivlendi.** |
| `caglarsarikaya/postman-collections` | 2025-09-09 | SOAP koleksiyonu (IETT + Eshot). Yeni endpoint dökümantasyonu yok. |

**Sonuç:** Tüm aktif İETT projeleri ya bizim kullandığımız SOAP'a bağımlı ya da idari baskıyla kapatılmış. **Hiçbir community projesi alternatif bir resmi feed kaynağı bulamamış.**

### Otobüsüm Nerede uygulaması (public bilgi)

- **Geliştirici:** İETT Genel Müdürlüğü (in-house, outsource firma yok).
- **Son güncelleme:** **2024-12-02 (v1.5.0)**.
- **Kullanıcı oyu:** **1.3/5 (6800+ review)**. Şikayetler "yanlış konum" + "şema yanlışlığı" yönünde — yani uygulama kendisi de İETT'nin RT veri kalite problemine maruz.
- **Gizlilik politikası:** "Geliştirici bu uygulamadan veri toplamıyor." Üçüncü taraf data partner belirtilmiyor.
- **Sonuç:** Mobil uygulama bile İETT'nin kendi verisini kullanıyor; yani o veri içinden çıkarsa elde edilebilir tek kaynak yine bu SOAP. Outsource bir API satıcısı yok.

### Diğer İstanbul kurumları (Metro, İDO, Şehir Hatları)

- **Metro İstanbul** (`metro.istanbul`): Public API yok, GTFS-RT yok, developer dökümantasyonu yok. Sadece schedule sayfaları.
- **İDO / Şehir Hatları:** Static GTFS olarak İBB'nin "Public Transport GTFS Data" dataset'inde yer alıyorlar (2025-03-12 son güncelleme). **RT feed yok.**

### İzmir / Ankara / EGO karşılaştırması

- **İzmir** (Eshot/IZBAN/TRAM): transit.land kayıtlı, sadece statik GTFS. RT feed yok.
- **Ankara EGO**: transit.land'de yer almıyor. Public API yok.
- **Sonuç:** Türkiye'de **hiçbir** belediye/operatör halka açık GTFS-RT yayınlamıyor. İstanbul "kapalı" olmasıyla yalnız değil — ülke genelinde durum aynı.

---

## Karar matrisi

| Bulgu kombinasyonu | Bu turdaki gerçekleşme | Sıradaki tur |
|---|---|---|
| P1: Resmi public RT API var | **YOK** — sadece bizim kullandığımız SOAP, yeni hiçbir endpoint yok | — |
| P2: GTFS-RT feed var | **YOK** — 2 hafta önce talep "SOAP kullan" diye kapatıldı | — |
| P3: 3rd-party feed var, lisans uygun | **YOK** — transit.land/MobilityDB Türkiye için sadece İzmir, hepsi static | — |
| **P4: Hiçbiri yok** | **EVET — durum tam olarak bu** | **Plan A polyline brief'i (Yol B), mapping "known limitation" olarak kabul** |

---

## Tavsiye

**Yol B (Plan A polyline) tek rasyonel sıradaki tur.** Üç turluk keşif zinciri P4'ü sağlam kanıtlarla netleştirdi:

1. **İBB tarafı kapalı, kapanma yönüne aktif tavır gösteriyor.** RT veri talebi 2 hafta önce SOAP'a yönlendirilerek kapatıldı; iettnext gibi alternatif çözüm üreten projeler "idari baskı ile" durduruldu. Yeni bir public API'nin kısa-orta vadede açılma olasılığı düşük.
2. **Mevcut SOAP'tan daha iyi bir data path yok.** Bizim cassette + rate limiter + parser + enrich zincirimiz zaten Türkiye'de bu veriye en disiplinli erişim mimarilerinden biri. Sorun veri kaynağında değil, mapping'in fundamental olarak heuristic olmasında (HatKodu doğrulanmış değil, sefer/durak korelasyonu var).
3. **Reverse engineering yolu (mobil uygulama endpoint capture) bu turun dışındaydı, ama iettnext örneği gösteriyor ki bu yol teknik olarak çalışsa bile sürdürülebilir değil — İBB aktif olarak engelliyor.** Yağız'ın bunu ayrı bir tartışma olarak bırakma kararı doğru pozisyon.
4. **Static GTFS güncellemesinin de İBB tarafında prioritize edilmediği görülüyor** (M3/M4/M5/M9 eksikliği için 2 ay boyunca cevap yok). Bu, İBB'nin transit data ürünü olarak GTFS ekosistemine yatırım yapmadığının bir başka sinyali.

**Pratik karar:** Plan A polyline (Yol B) brief'ini açıp 29B koridor görselleştirmesini polyline overlay + heatmap mimarisiyle çözmek. Bus mapping kalsın "known limitation" olarak ROADMAP/SPEC Ek A'ya işlensin, kullanıcıya transparan biçimde sunulsun (örn. "62 araç bu koridora **yakın**, mapping kesinliği kanıtlanamadı").

**Eğer ileride "tek tek araç başına HatKodu doğrulaması" zorunlu hale gelirse:** O zaman İBB ile bilateral data sharing anlaşması (ya akademik tez kanalı ya kurumsal partnership) konuşulabilir; reverse engineering ya da web scraping seçenekleri sürdürülebilir değil.

---

## Ek — Doğrulanmamış / takip edilebilir ipuçları

- **`Rednexie/iettnext` v2 (yaz 2026):** Geliştirici "tamamen open-source backend ile" v2 planlıyor. Eğer İBB ile uzlaşma sağlanırsa veya bypass yöntemi public hale gelirse, kendi mimarimiz için ders çıkarılabilir kaynak. Takip listesinde tutulabilir, **aksiyon yok**.
- **`b22d4cac-07ea-4317-82cb-2501d6c61a6d` (GTFS güncelleme talebi):** Eğer bu talep ileriki aylarda yeni bir resource yaratırsa (raylı hatlar dahil), static GTFS coverage'ımızı geliştirebilir. **Aksiyon yok**, takipte tut.
- **MobilityDatabase'in resmi REST API'sı (`api.mobilitydatabase.org/v1/search`):** Bu turda redirect/auth nedeniyle ulaşılamadı. Bir sonraki turda explicit cURL ile API token alınarak doğrulanabilir, ancak transit.land sonucu zaten "İstanbul yok" diyor; çok düşük marjinal değer.

---

## Suite kontrolü

Kod değişmedi, test koşulması pro forma — gerek yok.
