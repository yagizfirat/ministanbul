# 29B Spatial Sanity — Plan A öncesi ampirik ölçüm

**Tarih:** 2026-05-02
**Amaç:** Faz 5.5 Plan A polyline implementation'ı için spatial threshold parametresini empirik belirlemek. Yağız'ın "29B mapped araç güzergahından kilometrelerce uzakta" gözleminin sayısal teyidi/redi.

**Önkoşul:** Faz 5.5 patch turu tamamlandı (commit'ler `9c98c21`, `1c1bbe0`, `5e5c76d`). 29B 126 trip × 28 stop_times = 3.528 satır DB'de mevcut.

---

## Durak referans kümesi

29B canonical PK `iett:1562` üzerindeki tüm trip'lerin stop_times'larından deduplicated stop kümesi: **28 unique stop** (yalnız canonical PK).

7 varyantın tümü dahil edilince: **54 unique stop**. Ölçümlerde bu daha geniş küme kullanıldı (tolerantlı yaklaşım: bir vehicle herhangi bir 29B varyantına yakınsa 'yakın' sayılır).

**29B PK varyantları:**

| route_id | long_name |
|---|---|
| `iett:1562` | 4.LEVENT METRO - FATİH SULTAN MEHMET |
| `iett:1564` | ECLİPSE SİTESİ - FATİH SULTAN MEHMET |
| `iett:1567` | FATİH SULTAN MEHMET - 4.LEVENT METRO |
| `iett:1572` | FATİH SULTAN MEHMET - ECLİPSE SİTESİ |
| `iett:52301` | FATİH SULTAN MEHMET - 4.LEVENT METRO |
| `iett:52303` | 4.LEVENT METRO - FATİH SULTAN MEHMET |
| `iett:55379` | FATİH SULTAN MEHMET - 4.LEVENT METRO |

**İlk 5 stop:**

| stop_id | name | lat | lon |
|---|---|---:|---:|
| 659260 | 4.LEVENT METRO | 41.08383 | 29.00714 |
| 659093 | FABRİKALAR | 41.08001 | 29.01133 |
| 680932 | FABRİKALAR | 41.08018 | 29.01195 |
| 680871 | 4.LEVENT | 41.08752 | 29.00701 |
| 680926 | SULTAN SELİM MAHALLESİ | 41.09086 | 29.00599 |

---

## Ölçüm 1 — PoC referans noktaları (deterministic)

PoC raporundaki (`_research/2026-05-02-faz55-29b-poc.md`, Bölüm 5) B-1823 ve B-1827 koordinatları sabit referans olarak kullanıldı. PoC raporunda bu vehicle'lar Overpass-türetilmiş yol-snap polyline'a sırasıyla 1354m ve 1679m uzaktaydı. Şimdi durak-bazlı (Plan A) ölçümü:

| KapiNo | Lat | Lon | En yakın durak | Stop koordinatı | Plan A mesafesi | PoC polyline mesafesi | Delta |
|---|---:|---:|---|---|---:|---:|---:|
| B-1823 | 41.09712 | 29.00436 | SEYRANTEPE YOLU (293677) | (41.09584, 29.00567) | **180m** | 1354m | -1174m |
| B-1827 | 41.06985 | 29.01484 | FABRİKALAR (659093) | (41.08001, 29.01133) | **1168m** | 1679m | -511m |

---

## Ölçüm 2 — Canlı snapshot (Redis)

Redis key: `vehicles:all`
Snapshot timestamp: `2026-05-02T16:16:34Z`
Toplam vehicle: 6911
Mapped vehicle: 2726
29B mapped vehicle: **2**

**Canlı 29B vehicle'lar:**

| KapiNo | Lat | Lon | route_id | speed | En yakın durak | Mesafe |
|---|---:|---:|---|---:|---|---:|
| B-1823 | 41.06692 | 29.01369 | `iett:1562` | 0.0 | FABRİKALAR | **1469m** |
| B-1827 | 41.09976 | 28.98469 | `iett:1562` | 0.0 | SEYRANTEPE YOLU | **1812m** |

---

## Birleştirilmiş histogram (PoC + canlı)

Toplam 4 vehicle (2 PoC + 2 canlı):

| Bant | Vehicle sayısı | % |
|---|---:|---:|
| 0-100m | 0 | 0.0% |
| 100-300m | 1 | 25.0% |
| 300-500m | 0 | 0.0% |
| 500m-1km | 0 | 0.0% |
| 1km+ | 3 | 75.0% |

---

## Senaryo teşhisi

**γ — yapısal arşiv stale'liği teyit.** 75.0% vehicle >1km bandında. Plan A polyline tek başına yetmez — mapping'in kendisi yanlış stamp ediyor demektir. Bu durumda Plan A implement edilirken 'spatial threshold ihlal eden vehicle'ları route_id=None'a düşür' davranışı kritik (mevcut 5j-ii gibi ikinci bir filter katmanı). Mapping'in kendisini temizlemek için ayrı bir tur (örn. arşiv yerine bugünün gerçek seferleri) gerekebilir.

---

## Plan A implementation tavsiyesi

- **DİKKAT:** Plan A implementation'a geçmeden önce mapping katmanı incelemesi gerekli. %50+ vehicle 1km+ uzak demek, vehicle.timestamp ve interval bisect doğru çalışıyor olsa bile vehicle gerçekten o güzergahta DEĞİL.
- **Spatial filter zorunlu:** Plan A polyline + 500m threshold ile mapping'in `route_id=None`'a düşürülen oranını ölç. Beklenti: %50+ vehicle unmapped olacak — bu doğru davranış (şüphede None).
- **Mapping kaynak sorgusu:** arşiv-tabanlı yerine bugünün gerçek seferleri için ayrı bir veri kaynağı araştırılmalı (canlı GTFS-RT, İBB'nin başka bir API'si, vb.) — ayrı oturum konusu.

---

**Script:** `backend/scripts/sanity_29b_distance.py` (geçici, bu rapor üretildikten sonra silindi).
**Üretim zamanı:** 2026-05-02T16:17:12Z
