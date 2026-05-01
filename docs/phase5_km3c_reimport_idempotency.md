# Faz 5 KM3-c — `import_gtfs --force` Idempotency Check

**Tarih:** 2026-05-01
**Bağlam:** KM1'de `Calendar` tablosu manuel `_load_calendar` çağrısıyla doldurulmuştu (52 satır). `import_gtfs.py`'a wired edilmişti (`gtfs_calendar` TRUNCATE listesinde + `_load_feed` orchestration'da `_load_calendar` çağrısı) ama `--force` ile uçtan uca reimport hiç koşulmamıştı. Bu mini-faz onu kapatır.

---

## Sayım: BEFORE

| Tablo | Satır |
|---|---:|
| Agency | 9 |
| Calendar | 52 |
| Route | 9 773 |
| Shape | 953 |
| Stop | 22 458 |
| Trip | 150 012 |
| StopTime | 1 248 454 |

---

## Reimport çıktısı (öne çıkan satırlar)

```
[parse] Reading feeds via gtfs-kit...
  [public] parsing 8 CSV(s)
  [iett]   parsing 6 CSV(s)

[load] Opening atomic transaction...
  Wiping existing GTFS tables (TRUNCATE CASCADE)...

  [public] loading into DB...
    Frequency-based scheduling detected (2310 rows, 1230 unique trips), skipped in Phase 1 MVP.
    [public] 1 route(s) skipped (malformed route_id — embedded commas/newlines or >50 chars).
    [public] stops: total=7073, clean=7072, fixed=0, skipped-corrupt=1, skipped-oob=0 -> inserted 7072
    [public] 2 trips skipped (unknown route_id)
    [public] 11 stop_times skipped (missing trip/stop refs)
    [public] inserted: agencies=8, routes=499, stops=7073, trips=14387, stop_times=199969, calendar=49

  [iett] loading into DB...
    [iett] 4 intra-file duplicate route_id(s) — kept last occurrence.
    [iett] stops: total=15390, clean=0, fixed=15374, fixed-3dot=12, skipped-corrupt=4 -> inserted 15386
    [iett] 90 stop_times skipped (missing trip/stop refs)
    [iett] inserted: agencies=1, routes=9279, stops=15390, trips=135625, stop_times=1048485, calendar=3

=== Import Complete ===
  public routes=499, stops=7073, trips=14387, stop_times=199969
  iett   routes=9279, stops=15390, trips=135625, stop_times=1048485

  DB totals (after upsert merge):
    Agency     9
    Route      9773
    Stop       22458
    Shape      953
    Trip       150012
    StopTime   1248454
```

**Süre:** ~13 saniye (200 K + 1 048 K stop_times). Beklenen 5-10 dk büyük overshoot — gerçekte feed boyutu daha küçük + bulk_create verimli.

**Calendar import path teyidi:** `[public] inserted: ... calendar=49` ve `[iett] inserted: ... calendar=3` satırları `_load_calendar` çağrısının `_load_feed` orchestration'ında doğru yere wired olduğunu kanıtlıyor.

### Anormal/uyarı çıktısı (hepsi bilinen pattern'ler)

| Uyarı | Sayı | Bilinen sebep |
|---|---:|---|
| Public malformed route_id (embedded comma) | 1 | Faz 1 pattern (CSV parse hatası kaynağında) |
| Public corrupt stop (NaN coord) | 1 | Faz 1 pattern (`SİNPAŞ KORU KONUTL,` lat=nan) |
| Public skipped trips (unknown route_id) | 2 | İlk uyarıdan kaynaklı kaskat |
| Public skipped stop_times (missing FK) | 11 | Yukarıdaki kaskat |
| iETT intra-file duplicate route_id | 4 | Faz 1 pattern (kept last) |
| iETT corrupt stop coords | 4 | Faz 1 pattern (`direction: GİDİŞ` lat string'inde, exponent notation lon) |
| iETT skipped stop_times (missing FK) | 90 | Yukarıdaki kaskat |

Yeni patolojik durum **YOK**. Hepsi Faz 1'de tespit edilmiş, sanitize edici fonksiyonlarla absorbe edilen sızıntılar.

---

## Sayım: AFTER

| Tablo | Satır | Δ |
|---|---:|---:|
| Agency | 9 | 0 |
| Calendar | **52** | 0 |
| Route | 9 773 | 0 |
| Shape | 953 | 0 |
| Stop | 22 458 | 0 |
| Trip | 150 012 | 0 |
| StopTime | 1 248 454 | 0 |

---

## Sonuç

- [x] **İdempotent** (BEFORE = AFTER, 7/7 tablo)
- [x] **Calendar import path** doğru çalışıyor (`--force` içinde, `_load_feed` orchestration'ı `_load_calendar` çağırdı, 49 + 3 = 52 satır)
- [x] **TRUNCATE listesi** (`gtfs_stoptime, gtfs_trip, gtfs_shape, gtfs_stop, gtfs_route, gtfs_agency, gtfs_calendar RESTART IDENTITY CASCADE`) tüm tabloları temizleyip yeniden doldurdu — orphan satır yok.
- [x] **Realtime suite** reimport sonrası **155/155 yeşil**, gtfs suite **25/25 yeşil** (toplam 180/180). Mapping/spatial cache'lerin reimport sonrası invalidate olması beklenebilirdi ama test'ler pytest fixture DB'siyle çalıştığı için gerçek runtime cache'ten bağımsız geçti — **prod cache invalidation ayrı bir konu, bu test kapsamı dışı**.

**Notlar:**
- KM1'deki manuel `_load_calendar` injection'ı artık gereksiz — `manage.py import_gtfs --force` aynı sonucu kendi orchestration'ında üretiyor.
- 13 saniyelik tam reimport, dev döngüsünde feed yenileme/migration test akışını engellemiyor.
- Yeni borç notu **gerekmedi** — yapı temiz, idempotent, bilinen Faz 1 sızıntıları aynen absorbe edildi.
