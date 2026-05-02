# 29B Mapping Spatial Sanity — n=mapping buyuklugunde olcum

**Tarih:** 2026-05-02
**Amac:** Onceki tur n=4 (2 PoC + 2 canli) ile %75 uzakta cikmisti (gamma); bu tur n=mapping buyuklugune cikartildi. Iki set yan yana olculur: mapping arsiv atamasi (Set A) ve drift filter sonrasi canli pipeline ciktisi (Set B).

**Onkosul:** Faz 5.5 patch turu tamamlandi. Mapping cache (`snapshot_date=2026-04-25, snapshot_day_type=saturday`) yeterince taze (bugun = Cumartesi, mapping = gecen Cumartesi, gun-tipi uyumlu).

---

## 1. Durak referans kumesi

29B 7 PK varyantinin tum trip'lerinin stop_times'larindan deduplicated stop kumesi: **54 unique stop**. Tolerantli yaklasim — vehicle herhangi bir 29B varyantina yakinsa 'yakin' sayilir.

---

## 2. Set A — mapping arsiv atamasi

`iett:mapping:current` JSON'unda su anki TR saatinde (`now_sec=72986`, 20:16:26) aktif 29B intervalli KapiNo: **2**.

Toplam mapping by_kapi: 4942. Bugun herhangi bir saatte 29B gorevi olan KapiNo: 2.

Set A KapiNo'larinin canli snapshot'ta bulunabilirligi:

- Snapshot'ta bulunan: 2
- Snapshot'ta YOK (vehicle bildirim yapmiyor): 0

---

## 3. Set B — canli pipeline 29B mapped vehicle

`vehicles:all` snapshot timestamp: `2026-05-02T17:15:38Z`
Total: 6911, mapped: 2386
29B PK ile mapped vehicle: **2**

---

## 4. Set fark analizi

- |A| (mapping aktif, snapshot'ta bulunan) = 2
- |B| (canli pipeline mapped) = 2
- |A and B| = 2
- Yalnizca A'da (drift filter eledi): **0**
- Yalnizca B'de (mapping aktif degil ama pipeline mapped): **0**

---

## 5. Histogram — Set A

n=2 vehicle (mapping aktif + canli pozisyon var)

| Bant | n | % |
|---|---:|---:|
| 0-100m | 0 | 0.0% |
| 100-300m | 0 | 0.0% |
| 300-500m | 0 | 0.0% |
| 500m-1km | 0 | 0.0% |
| 1km+ | 2 | 100.0% |

## 6. Histogram — Set B

n=2 vehicle (canli pipeline 29B PK mapped)

| Bant | n | % |
|---|---:|---:|
| 0-100m | 0 | 0.0% |
| 100-300m | 0 | 0.0% |
| 300-500m | 0 | 0.0% |
| 500m-1km | 0 | 0.0% |
| 1km+ | 2 | 100.0% |

---

## 7. Senaryo teshisi

**S3** — S3 — yapisal arsiv stale'ligi: mapping arsivinin kendisi yanlis, drift filter yakalayamiyor cunku drift olmadan da yer yanlis. Yol C kesin gerekli.

Set A: 0.0% <500m, 100.0% >1km
Set B: 0.0% <500m, 100.0% >1km

---

## 8. Plan A/B/C tavsiye

**YOL C zorunlu.** Plan A tek basina yetmez — mapping arsivinin kendisi yanlis. GetHatOtoKonum_json (Kesif 7) sonucu olumluysa canli kaynak adapter'i; degilse Plan A + agresif spatial filter (yari cozum, %50 vehicle unmapped'e duser).

---

**Script:** `backend/scripts/sanity_29b_mapping.py` (gecici, rapor uretildikten sonra silindi).
**Uretim zamani:** 2026-05-02T17:16:26Z
