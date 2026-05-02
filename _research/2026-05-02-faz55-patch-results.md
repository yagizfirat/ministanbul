# Faz 5.5 stop_times patch turu — sonuçlar

**Tarih:** 2026-05-02
**Patch kapsamı:** `apps/gtfs/management/commands/download_gtfs.py` — stop_times için ZIP-prefer resolver. `import_gtfs.py` autodetect doğrulandı, dokunulmadı.

---

## Baseline (patch öncesi)

| Metrik | Değer |
|---|---:|
| StopTime total | 1.248.454 |
| Trip total | 150.012 |
| Route total | 9.773 |
| IETT StopTime | 1.048.485 |
| IETT Trip | 135.625 |
| IETT Route (bus) | 9.274 |
| IETT bus unique short_name | 1.095 |
| **IETT bus short_name with stop_times** | **139 (%12.69)** |
| 29B Trip / with stop_times | 126 / 0 |
| Metrobüs (34, 34A, 34BZ, 34G, 34Z) | 0 stop_times |

Local feed dosya boyları:
- `data/gtfs/iett/stop_times.csv`: 1.048.576 satır (header dahil = 2^20, Excel limit)
- `data/gtfs/iett/trips.csv`: 135.626 satır (truncated DEĞİL, ham GTFS)

CKAN dataset'inde aynı `iett-gtfs-verisi` altında:
- `stop_times` resource (CSV format): 25.97 MB
- `stop_times` resource (ZIP format): 22.75 MB → açılmış 6.155.692 data satırı

---

## Patch sonrası

Reimport: `download_gtfs --feed iett --force` + `import_gtfs`. ZIP indirildi (21.7 MB), single-file extract edildi (`stop_times.txt` → `stop_times.csv` rename), import autodetect canonical UTF-8 + virgül formatını tanıdı.

İlk run'da bir cosmetic crash oldu: `→` U+2192 karakteri Windows cp1254 console encoding'inde fail. shutil.move ZATEN ÇALIŞMIŞTI (dest dosyası 144 MB / 6.155.693 satır olarak yenilenmişti), sadece SUCCESS print satırı patladı. ASCII'ye çevirildi, ikinci run sha256 match → UNCHANGED. Diğer hat boyutu fark yok.

| Metrik | Baseline | Patch sonrası | Delta |
|---|---:|---:|---:|
| StopTime total | 1.248.454 | **6.354.672** | ×5.09 |
| IETT StopTime | 1.048.485 | **6.154.703** | ×5.87 |
| IETT Trip-level coverage | %13.96 | **%100.00** | tam |
| IETT bus short_name coverage | 139/1095 (%12.69) | **796/1095 (%72.69)** | ×5.7 |
| IETT bus route_id coverage | (ölçülmedi) | 2880/9274 (%31.05) | (kalan 6394 PK trip'siz history) |
| 29B Trip with stop_times | 0/126 | **126/126** | tam |
| 29B StopTime | 0 | **3.528** | — |
| Metrobüs (5 hat toplam) | 0 | **334.758** | tam |

Local stop_times.csv: 25 MB → **144 MB** (×5.76).

## Trip skip oranı (FK lookup)

İmport komutu `[iett] 989 stop_times skipped (missing trip/stop refs)` log etti. 6.155.692 satırın 989'u (%0.016) trip_id ya da stop_id FK'sı DB'de bulunmadığı için atlandı. Beklenen kabul edilebilir gürültü; canonical GTFS feed'in iç tutarsızlıkları (örn. orphan stop_id reference). Eski Excel-truncated CSV'de 90 skipped vardı (%0.009); ölçek farklı, oran benzer.

## Test suite

- Backend: 203/203 yeşil (165 realtime + 38 gtfs)
- Frontend: 210/210 yeşil
- Toplam: 413/413

İmport autodetect log'u (kritik):

```
[iett] parsing 6 CSV(s) from iett/
    agency.csv           encoding=utf-8      sep=','
    calendar.csv         encoding=utf-8      sep=';'
    routes.csv           encoding=utf-8-sig  sep=';'
    stop_times.csv       encoding=utf-8      sep=','     ← yeni canonical
    stops.csv            encoding=utf-8-sig  sep=';'
    trips.csv            encoding=utf-8-sig  sep=';'
```

Sadece `stop_times.csv` formatı değişti (utf-8 + virgül); diğer 5 dosya eski Excel-style'da kaldı. `import_gtfs.py` autodetect zinciri patch gerektirmedi.

## 29B durak listesi (Faz 5.5 Plan A doğrulaması)

29B canonical PK `iett:1562` üzerindeki ilk trip için:

```
Trip 445933190 (headsign=FATIH SULTAN MEHMET): 28 stops
  seq=  1  4.LEVENT METRO              (41.08383, 29.00714)
  seq=  2  FABRIKALAR                  (41.08001, 29.01133)
  seq=  3  FABRIKALAR                  (41.08018, 29.01195)
  ...
  seq= 26  NARIN KÖPRÜSÜ              (41.09229, 29.03307)
  seq= 27  DUMLUPINAR İLKOKULU        (41.09281, 29.03757)
  seq= 28  FATIH SULTAN MEHMET         (41.09348, 29.04129)
```

PoC raporundaki referans noktalar (4.LEVENT METRO 41.083820, 29.006832 + FSM CIKIS 41.091609, 29.073163) DB ile birebir uyumlu (4.Levent) ya da yakın (FSM CIKIS PoC'de "SANAL DURAK" referans noktasıydı, gerçek son durak 29.041'de). 28 durak boyunca güzergah artık SQL ile çıkarılabilir; Plan A için uygun.

## Sonuç

Faz 5.5'in zayıf halkası ortadan kalktı. Implementation oturumu Plan A ile (durak-bazlı polyline) `python manage.py build_stop_polylines` komutu yazılarak başlayabilir. Plan B (OSM Overpass + pgrouting) artık sadece snap-quality regresyon durumunda yedek; KM5-a/b/c/d alt-fazları o zamana kadar dondurulmuş.
