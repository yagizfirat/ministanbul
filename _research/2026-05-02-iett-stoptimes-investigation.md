# İETT stop_times import incelemesi — Faz 5.5 öncesi tanı

**Tarih:** 2026-05-02
**Yöntem:** Django ORM + local file inspection + CKAN package_show metadata + tek seferlik stop_times.zip indirme. Geçici scratch dosyaları (`_tmp_probe/`, `/tmp/iett_stop_times.zip`) inceleme sonunda silindi.
**Hedef:** İETT'nin stop_times %1.5 coverage probleminin yapısal mı (feed'de yok) yoksa import sürecinde mi (feed'de var, DB'ye yazılmadı) olduğunu net olarak ortaya koymak. Sonuç Faz 5.5 stratejisini belirler.

---

## Bölüm 1 — Mevcut DB durumu

| Metrik | Değer |
|---|---:|
| Total `StopTime` row sayısı | 1.248.454 |
| IETT StopTime | 1.048.485 |
| Public StopTime | 199.969 |
| IETT bus route total (`agency=IETT, route_type=3`) | 9.274 |
| IETT bus route en az bir trip'i `stop_times`'lı | **516 (%5.56)** |
| IETT Trip total | 135.625 |
| IETT Trip with stop_times | **18.934 (%13.96)** |
| Public Trip coverage | 14.380 / 14.387 (%99.95) |

Önceki ROADMAP'teki "139/9274 covered hat" rakamı muhtemelen daha sıkı bir filter (full trip coverage) ile alınmıştı; bugün ölçüm "en az 1 trip stop_times'lı" route sayısı 516.

**29B özelinde:** 7 PK varyantın 5'inde Trip yok, kalan 2'sinde (`iett:1562`, `iett:1567`) toplam 126 Trip var ama **0 StopTime**. Top 10 IETT bus route'da ortak pattern: çok büyük trip count (20K-27K), küçük stop_times alt kümesi (200-380 trip). Açıklama bir sonraki bölümde.

---

## Bölüm 2 — Local feed dosya kontrolü

`data/gtfs/iett/` klasörü:

```
agency.csv      114 B
calendar.csv    232 B
routes.csv      794 KB
stop_times.csv  25 MB    ← 1.048.575 data satırı
stops.csv       1.5 MB
trips.csv       5.6 MB   (135.625 satır)
```

Public feed'de ek olarak `frequencies.csv` ve `shapes.csv` var; IETT'de yok (Ek A.4 ile uyumlu, shape-less).

**Anomali:** stop_times.csv satır sayısı **1.048.575**. Bu **2^20 - 1**, yani **Excel'in MAX_ROWS limit'inin 1 eksiği** (Excel 2007+ XLSX format 1.048.576 satır). Şüphe: dosya Excel'de "Save As CSV" ile yazılmış ve veri truncate olmuş.

**Encoding/format sniff:**
- BOM: `\xef\xbb\xbf` (UTF-8 BOM, Excel imzası)
- Delimiter: `;` (Excel Turkish locale "List separator")
- Header: `trip_id;stop_id;stop_sequence;arrival_time;departure_time;timepoint`

**CSV ⇔ trips.csv cross-reference:**
- stop_times.csv distinct trip_id: **18.934**
- trips.csv distinct trip_id: 135.625
- Intersection: 18.934 (orphan yok)
- trips.csv'de olup stop_times.csv'de olmayan: **116.691 trip**

Yani stop_times.csv 18.934 trip için satır içeriyor; geri kalan 116.691 trip için CSV dosyasında satır yok.

---

## Bölüm 3 — Import komutu kod incelemesi

`apps/gtfs/management/commands/import_gtfs.py:_load_stop_times` (lines 712-752):

```python
def _load_stop_times(self, df: pd.DataFrame, trip_pk: dict, stop_pk: dict, label: str) -> int:
    if df.empty: return 0
    skipped = 0
    for r in df.itertuples(index=False):
        tid = str(r.trip_id); sid = str(r.stop_id)
        tpk = trip_pk.get(tid); spk = stop_pk.get(sid)
        if tpk is None or spk is None:
            skipped += 1; continue
        yield StopTime(...)
    if skipped:
        self.stdout.write(WARNING(f"{skipped} stop_times skipped"))
    StopTime.objects.bulk_create(objs, batch_size=BATCH)
```

**Bug yok.** itertuples ile tüm DataFrame iterate ediliyor, FK lookup miss durumunda skip + log. CSV'den DB'ye geçişte:
- stop_times.csv data: 1.048.575 satır
- DB IETT StopTime: 1.048.485
- Kayıp: 90 satır (%0.009) — `trip_pk.get(tid) is None or stop_pk.get(sid) is None` filter'ından geçen orphan FK'ler. Beklenen ve dökümante.

**Sonuç:** İmport sıfır mantık hatasıyla çalışıyor; feed dosyasında ne varsa DB'ye yazılmış. Eksiklik feed dosyasının kendisinde.

---

## Bölüm 4 — CKAN metadata + download komutu kapsamı

CKAN `iett-gtfs-verisi` dataset'i `package_show` API çağrısı (HTTP GET, 2026-05-02):

| Resource | Format | Boyut | last_modified |
|---|---|---:|---|
| agency | CSV | 114 B | 2024-03-13 |
| calendar | CSV | 232 B | 2026-03-17 |
| routes | CSV | 812 KB | 2026-03-17 |
| stops | CSV | 1.52 MB | 2026-03-17 |
| trips | CSV | 5.82 MB | 2026-03-17 |
| stop_times | CSV | 25.97 MB | 2026-03-17 |
| **stop_times** | **ZIP** | **22.75 MB** | **2026-03-17** |

`download_gtfs.py` lines 9-10 (Faz 1'de yazılmış yorum):

> "A redundant `stop_times.zip` resource exists (gzip of stop_times.csv only, not a full GTFS bundle) — we ignore it and pull the raw CSV."

**Bu varsayım yanlış çıktı.** stop_times.zip tek seferlik indirildi ve incelendi:

| Metrik | stop_times.csv (Excel-truncated) | stop_times.zip içeriği (FULL GTFS) |
|---|---:|---:|
| Compressed size | — | 22.75 MB |
| Uncompressed size | 25 MB | **143 MB** |
| Data row count | 1.048.575 | **6.155.692** |
| Distinct trip_id | 18.934 | **135.625** |
| Trip coverage | %13.96 | **%100.00** |
| Delimiter | `;` (semicolon) | `,` (comma, GTFS standard) |
| BOM | UTF-8 BOM | yok |
| Header content | aynı sütunlar |
| Inner filename | — | `stop_times.txt` |

**Cross-check sonucu:**
- stop_times.csv'deki trip_id seti, stop_times.zip içerik trip_id setinin **TAM ALT KÜMESİ** (`csv.issubset(zip) == True`)
- ZIP, CSV'de olmayan **116.691 ek trip için stop_times** içeriyor
- ZIP feed'in 135.625 trip'inin **%100'ünü** kapsıyor (orphan: 0)

**Mekanizma:** İBB'nin pipeline'ı muhtemelen şu sırayla işliyor:
1. GTFS export → `stop_times.txt` (gerçek tam veri, 6.1M satır, virgül delimiter, no BOM)
2. Bunun bir kopyası `stop_times.zip` olarak yayınlanıyor (asıl dosya, GTFS standart)
3. Aynı veri Excel ile açılıyor → ilk **2^20 satır = 1.048.576** kaydedilebiliyor (XLSX limit)
4. Excel "Save As CSV" ile dışa aktarılıyor → `stop_times.csv` (truncate edilmiş, semicolon delimiter, BOM eklenmiş, Türkçe locale)
5. Her iki dosya da aynı CKAN dataset'ine konuyor

`stop_times.csv` resource'u **veri kayıplı bir Excel artefact'i**. Asıl veri `stop_times.zip` resource'unda.

`download_gtfs.py` CKAN'dan sadece `format == "CSV"` resource'larını çekiyor (line 202: `[r for r in all_res if (r.get("format") or "").upper() == "CSV"]`); `stop_times.zip` (format=ZIP) bu filter'a takılıyor, hiç indirilmedi.

---

## Bölüm 5 — Tanı: **(II) Resource var, indirilmemiş**

stop_times.zip CKAN'da mevcut, last_modified güncel (2026-03-17), feed'in tam veri kaynağı. download_gtfs onu format filter'ı yüzünden atlıyor; import_gtfs sadece truncated CSV'yi okuyor.

**Bu Faz 5.5'in zayıf halkasını ortadan kaldırır:**
- Coverage %13.96 → **%100** (135.625 trip için stop_times)
- 9.274 IETT bus route → her birinin başlangıç/bitiş stop'una DB'den otomatik erişim
- Faz 5.5'te headsign-tabanlı geo-coding heuristic'e gerek yok
- Per-route shortest path için referans noktalar `stop_sequence=1` ve `MAX(stop_sequence)` ile direkt çıkar

---

## Sonraki adım önerisi

**Tek bir kısa patch turu** (3-5 saat):

1. **`download_gtfs.py` patch (kısa):**
   - Format filter'ını `CSV` ile sınırlamak yerine her resource için `url_filename` lookup yap
   - `stop_times.zip` için özel branch: indir, içindeki `stop_times.txt`'i extract, `stop_times.csv` üstüne yazma yerine **ayrı dosya olarak sakla** ya da CSV'yi sil + ZIP içeriğini canonical sakla
   - Pratik öneri: `expected_files`'a `stop_times.zip` ekle, indirilen ZIP'i otomatik `stop_times.txt`'e extract et (Excel-CSV'i kullanma)

2. **`import_gtfs.py` patch (mikro):**
   - stop_times için yeni format desteği: virgül delimiter, BOM yok (mevcut `pd.read_csv` zaten encoding/delimiter sniff yapıyorsa otomatik çalışır — kontrol edilmeli)
   - Ya da explicit `delimiter=","` ve `encoding="utf-8"` parametrelerini stop_times için kullan

3. **Reimport:**
   - `python manage.py download_gtfs --feed iett --force`
   - `python manage.py import_gtfs --feed iett`
   - Beklenen: IETT StopTime 1.048.485 → ~6.155.000 (×5.87)
   - DB boyutu artışı: ~50-80 MB (StopTime tablosu)

4. **Sanity test:**
   - 29B'nin 126 trip'i için stop_times kontrolü
   - Random 10 IETT bus hat için başlangıç/bitiş stop name + lat/lon kontrolü
   - Realtime suite 165/165 (test'ler StopTime sayısına bağımlı değil, etkilenmez)

5. **Faz 5.5 implementation**:
   - Strateji A (mega-bbox + per-route Dijkstra) DB'den otomatik referans noktaları okuyabilir
   - Headsign-heuristic gereksiz
   - 9.274 hat için %100 otomatik coverage
   - Tahmin 1 hafta yerine 4-5 gün

**Sonraki oturum hedefi:** `download_gtfs.py` + `import_gtfs.py` patch'leri (test suite yeşil kalmalı, mevcut 165 + 210), reimport, sanity ölçümleri. Faz 5.5 implementation'a sağlam zemin.

---

## Açık not

Bu rapor 1 HTTP GET (CKAN package_show metadata, ~10 KB) + 1 download (stop_times.zip, 22.75 MB) yaptı — toplam ~23 MB ağ trafiği. İBB rate limit'i etkilemez (CKAN open data portalı, public feed).

Excel truncation bulgusu yeni bir Ek A maddesine değer: **Ek A.16 — İBB feed Excel-CSV truncation (stop_times)**. SPEC ve ROADMAP güncelleme bir sonraki oturumda patch tamamlandığında yapılır.
