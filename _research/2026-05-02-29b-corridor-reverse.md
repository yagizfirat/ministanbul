# 29B Koridoru Ters Sorgu — gercek araclar nerede

**Tarih:** 2026-05-02
**Amac:** "29B'ye mapped" deyil, "29B koridorunda" sorusunu sorarak mapping coverage'ini baska acidan olcmek. alpha vs beta karar zemini.

**Onkosul:** Onceki turun S3 teshisi (mapping yapisal arsiv stale'ligi). Bu tur S3'u tamamlayan bilgi: koridorda gercek araclar var mi, varsa hangi etikete sahipler?

---

## Setup

- 29B durak referans seti: **54 unique stop** (7 varyant union)
- Buffer: **200m** (durak cevresi koridor genisligi)
- Snapshot: `vehicles:all`, ts=2026-05-02T18:49:48Z
- Total fleet: 6911, mapped: 1764

---

## Sayilar

- Tum IETT fleet: **6911**
- 29B koridorunda (200m buffer): **62**

**Dagilim (koridor icindeki vehicle'lar):**

| Kategori | n | % |
|---|---:|---:|
| 29B'ye mapped (7 varyant union) | 0 | 0.0% |
| Baska hatlara mapped | 23 | 37.1% |
| Unmapped (route_id=None) | 39 | 62.9% |

**Baska hatlara mapped olanlar — top 10:**

| route_id | short_name | n |
|---|---|---:|
| `iett:23909` | 500T | 7 |
| `iett:2356` | 42T | 2 |
| `iett:2201` | 40B | 2 |
| `iett:53718` | 36Z | 2 |
| `iett:1440` | 22B | 1 |
| `iett:2878` | 58N | 1 |
| `iett:2299` | 41ST | 1 |
| `iett:56402` | 50H | 1 |
| `iett:1655` | 30A | 1 |
| `iett:3616` | 98B | 1 |

---

## Senaryo

**beta** — beta — mapping coverage kotu, koridordaki vehicle'larin cogu hic mapping atayamamis. Spatial filter sadece zaten az olan 29B etiketini eler. Plan A yarim cozum bile degil — mapping kaynak degisikligi gerekli.

---

## Karar (siradaki tur)

- **Mapping kaynak degisikligi zorunlu.** Plan A spatial filter ile bile yarim cozum degil — koridorda zaten cok az 29B etiketli vehicle var, filter onlari da elerse ekranda hicbir sey kalmaz.
- GTFS-RT VehiclePositions Istanbul icin var mi, baska CKAN dataset, community projeleri arastirmasi gerekli (ayri tur).

---

**Script:** `backend/scripts/probe_29b_corridor.py` (gecici, rapor uretildikten sonra silindi).
**Uretim zamani:** 2026-05-02T18:50:05Z
