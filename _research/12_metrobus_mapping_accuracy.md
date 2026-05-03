# 12 — Metrobüs mapping doğruluğu spot kontrolü

**Tarih:** 2026-05-03
**Tetik:** v0.8.0 Faz 5.5 KM5-a karar gate'i (ROADMAP KM5-b risk notu — "metrobüs için %30+ yanlış çıkarsa metrobüs de kütleye dahil").
**Konum:** Bu rapor SPEC Ek A.18'in metrobüs daraltılmış β-lite ölçümüdür; normal İETT bus β'sı (Ek A.18 referans %53 yanlış) ile aynı yöntemle karşılaştırılır.

## Yöntem

Mapping cache `iett:mapping:current`'tan METROBUS_SHORT_NAMES (10 hat) için stamped tüm vehicle'lar (`vehicles:all`) çekilir. Her hat için kanonik koridor polyline'ı türetilir: shape_id metrobüs için boş (Spec Ek A.4), bu yüzden en uzun stop_times sequence'a sahip trip'in stop koordinatlarından PostGIS LineString (straight-line) üretilir. Vehicle'ın anlık konumu PostGIS `ST_Distance(geometry::geography, polyline::geography)` ile metre cinsi dik mesafe ile ölçülür. Eşikler: <200m doğru, 200-500m şüpheli, >500m yanlış.

## Veri kümesi

- **Snapshot:** `2026-05-03T09:21:07Z` (cumartesi, 12:21 IST), `vehicles:all` 6911 araç / 2413 mapped
- **Mapping cache:** `snapshot_date=2026-04-25` (saturday day_type)
- **Metrobüs sample:** 181 atanmış vehicle (4 hat boş — 34A/34B/34Z `vehicles:all`'da yok, 34T/34U trip'siz)
- **Normal bus sample:** 2000 vehicle (metrobüs hariç, İETT bus mapped)
- **Script:** [`_research/scripts/12_metrobus_mapping_accuracy.py`](scripts/12_metrobus_mapping_accuracy.py)

## Sonuç tablosu — metrobüs hat bazında

| Hat | n | median (m) | p90 (m) | p99 (m) | %ok (<200m) | %susp (200-500m) | **%wrong (≥500m)** |
|---|---:|---:|---:|---:|---:|---:|---:|
| 34   |    1 |     32 |       32 |        32 | 100.0 |   0.0 |   **0.0** |
| 34A  |    – |      – |        – |         – |     – |     – |       –   |
| 34AS |   70 |    102 |    7912  |     9506  |  71.4 |  12.9 |  **15.7** |
| 34B  |    – |      – |        – |         – |     – |     – |       –   |
| 34BZ |   36 |    126 |    8337  |    10242  |  52.8 |   8.3 |  **38.9** |
| 34C  |   12 |    258 |   10311  |    10490  |  50.0 |  16.7 |  **33.3** |
| 34G  |   62 |     73 |     530  |      578  |  71.0 |  11.3 |  **17.7** |
| 34T  |    – |      – |        – |         – |     – |     – |       –   |
| 34U  |    – |      – |        – |         – |     – |     – |       –   |
| 34Z  |    – |      – |        – |         – |     – |     – |       –   |

**TOPLAM (181 vehicle):** median **96 m**, p90 **8273 m**, p99 **10485 m**, max **11206 m** — **%ok=66.3, %susp=11.6, %wrong=22.1**

### Hat başına worst-3 (KapiNo, mesafe_m)

- **34BZ**: M4898 (11206), M4606 (8451), O5056 (8352)
- **34C**: M3007 (10490), O5038 (10483), M3093 (8766)
- **34AS**: M4652 (9532), M3069 (9494), M3085 (9490)
- **34G**: O5018 (593), M3121 (568), M3189 (559)
- **34**: M3090 (32) — sadece 1 vehicle

## Normal bus β karşılaştırması

Aynı yöntem, aynı eşikler, sample=2000 (metrobüs hariç İETT bus mapped):

| Kategori | n | median (m) | p90 (m) | p99 (m) | %ok | %susp | **%wrong** |
|---|---:|---:|---:|---:|---:|---:|---:|
| **Metrobüs** (10 hat whitelist)   |  181 |   96 |  8273 | 10485 | 66.3 | 11.6 | **22.1** |
| **Normal İETT bus** (sample=2000) | 2000 |  597 |  7322 | 15601 | 42.8 |  6.1 | **51.1** |

Normal bus β'sı SPEC Ek A.18'deki %53 referansıyla tutarlı (β-lite, brief eşikleri 200/500m).

**Metrobüs normal bus'tan ~2.3× daha doğru** ama mutlak değer **mükemmel değil**. Median 96m gerçekten çok iyi (vehicle'ların yarıdan fazlası polyline'a 100m içinde). Ama dağılım çift modlu: bir kısım vehicle koridorda, başka kısım 8-11km uzakta — Yağız'ın B-184 / 98B / 14.5km gözleminin metrobüs versiyonu (örn. M4898 / 34BZ / 11.2km).

## Variant seçim notları

Polyline türetiminde `pick_canonical_polyline(short_name)` her hat için en çok stop'a sahip trip'i seçer (gidiş/dönüş ayrımı yapmadan, tek varyant):

- **34** → trip=446049097, 27 stop, long_name='AVCILAR - ZİNCİRLİKUYU'
- **34A** → trip=446044564, 20 stop, long_name='EDIRNEKAPI GARAJI - SÖĞÜTLÜÇEŞME' (UTF mojibake düzeltildi)
- **34AS** → trip=446005192, 34 stop, long_name='AVCILAR - SÖĞÜTLÜÇEŞME'
- **34B** → trip=446028983, 13 stop, long_name='AVCILAR - B.SONDURAK'
- **34BZ** → trip=445997934, 37 stop, long_name='ZİNCİRLİKUYU - B.SONDURAK'
- **34C** → trip=446031478, 29 stop, long_name='EDİRNEKAPI GARAJI - B.SONDURAK'
- **34G** → trip=445999287, 44 stop, long_name='nan' (feed bozuk değer; trip'in stop'ları sağlam)
- **34T** → trip yok (route'lar trip'siz, DB'de servis kayıtsız)
- **34U** → trip yok (route'lar trip'siz)
- **34Z** → trip=446044581, 8 stop, long_name='SÖĞÜTLÜÇEŞME - ZINCIRLIKUYU' (atanmış vehicle yok bu snapshot'ta)

Tek yön seçimi gidiş-dönüş ayrımı yapmaz; metrobüs koridoru izole ve aynı yolu paylaşır, ters yön penaltısı ihmal edilebilir (tipik durakta <50m offset).

## Karar dalı önerisi

Brief eşiklerine göre:

| Bulgu | Öneri |
|---|---|
| %wrong < 10  | KM5-a aynen, whitelist exception kalır |
| **%wrong 10-30** | **sınır vaka, Yağız tartışsın (hangi hatlar kötü?)** |
| %wrong ≥ 30  | metrobüs de retire, KM5-a basitleşir |

**Sonuç: Sınır vaka.** Toplam %22.1 brief'in 10-30 aralığında. Karar tek başına tabloya bakarak verilemez; alt-bulgular hat seviyesinde ayrışıyor:

- **İyi metrobüs hatları (kütle altında %18 ve aşağı):** 34 (n=1, anlamsız), 34AS (%15.7, p90 7912m'ye rağmen median 102m), 34G (%17.7 ve **p90=531m** — uzak kuyruk kısa, en sağlam hat)
- **Eşiği geçen kötü hatlar (≥%30):** 34BZ (%38.9, n=36), 34C (%33.3, n=12) — küçük sample ama net trend
- **Ölçülemeyen hatlar:** 34A, 34B, 34Z (atanmış vehicle yok bu snapshot'ta), 34T, 34U (DB'de trip'siz, mapping pratikte boşa çıkar)

### Tavsiye edilen yön — KM5-a ROADMAP'i kısmi koru

ROADMAP §KM5-b "metrobüs whitelist+categorize" planı, tüm 10 hattı tek blok olarak ele alıyor. Bulgu bu monolitik yaklaşımı **kısmen reddediyor**:

1. **Whitelist exception KALSIN** ama UI sözleşmesi kullanıcıya garanti vermesin: metrobüs popup'ında "Mapped 34BZ — yaklaşık konum, ~%22 oranında yanlış olabilir" gibi disclaimer ya da yumuşatma. Ya da bunu yapmaya gerek yoksa, en azından **34BZ + 34C** için ek inceleme.
2. **34BZ + 34C için detay ölçüm** (sonraki tur, gerekirse): bu iki hattın "uzak kuyruk" vehicle'ları gerçekten "depot'a gidiyor" mu, yoksa "yanlış stamped" mı? `M4898`'in 30 dk konum geçmişi ile spot doğrulama (önceki tur'daki spatial inference PoC altyapısı ile, 1-2 saat).
3. **34T + 34U** mapping'den çıkarılabilir (trip'siz hatlar, DB'de servis kaydı yok — pratikte zaten çıkmış, ama whitelist'te tutmak kafa karıştırıcı).
4. **Frontend renk + filtre:** metrobüs antrasit gri kalır; %22 oranındaki yanlış stamped vehicle'lar koridor görselinde "yanlış yerde antrasit araba" olarak görünür. Bu görsel kabul edilebilir mi → Yağız'ın UX kararı (B-184 / 98B oranında dramatik değil ama görünür olur).

### Karşı argüman — metrobüs de retire

Eğer Yağız "%22 hâlâ kabul edilemez, sözleşme net olmalı (popup'ta hat söylüyorsa doğru söylemeli)" derse, metrobüs de kütleye dahil edilir:

- KM5-a basitleşir: "tüm İETT bus mapping retire" tek satır, whitelist gerekmez.
- METROBUS_SHORT_NAMES sabiti silinir, frontend filtre paneli "🟡 İETT Otobüs (n)" tek kategori olur.
- Sonraki durak özelliği (KM5-c) metrobüs için iptal edilir; sadece raylı + vapur + füniküler.
- v0.8.0 vizyonu sadeleşir, tek bir tutarlı sözleşme: "İETT otobüs ve metrobüs için canlı GPS gösterilir, hat etiketi gösterilmez".

Bu yön KM5-c kapsamını ~%30 kısaltır.

## Sınır ve caveat'lar

- **Tek snapshot:** Bu ölçüm tek anlık snapshot (cumartesi öğleden sonra). 30 dk consistency layer eklemek dağılımın "uzak kuyruğunun" gerçekten yanlış stamped mı yoksa geçici manevra mı olduğunu netleştirir (önceki tur PoC altyapısı vardı, silinmedi referans).
- **Cumartesi düşük servis:** 34A, 34B, 34Z atanmış vehicle yok — bu hatların hafta içi davranışı farklı olabilir. Hafta içi peak hour'da ölçüm tekrarı %wrong'ı 10 puan oynatır mı bilinmiyor.
- **Polyline türetimi straight-line:** Stop'lar arası kıvrımlı yollarda mesafe biraz şişer (örn. metrobüs Boğaz Köprüsü S-eğrisi). 200m eşiği bu noise'a karşı yumuşak; 500m eşiği yapısal hatayı yakalar.
- **34G long_name='nan':** GTFS feed'inde bu hat için `route_long_name` literal string `'nan'`. Trip'in stop'ları sağlam, ölçüm geçerli; `nan` görüntüleme bug'ı UI'a yansıyacaksa ayrı düzeltme.

## Karar gerektirenler

1. **KM5-b plan:** Monolitik whitelist mi, hat-bazlı seçici whitelist (34G + 34AS sağlam, 34BZ + 34C şüpheli) mi, yoksa metrobüs de retire mı?
2. **34BZ + 34C için detay ölçüm:** Sonraki tur açılsın mı, yoksa "%22 yeter, karara baz olarak kullan" mı?
3. **Hafta içi tekrar:** Pazartesi peak hour'da aynı ölçümün koşulması bekleniyor mu, yoksa cumartesi sample'ı yeterli mi?

Karar açıkça brief'in 10-30 aralık tanımına uyuyor, dolayısıyla mekanik karar mümkün değil — Yağız'ın UX vs ölçeklenebilirlik dengesi kararı.
