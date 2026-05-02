# Yol B Implementation Öncesi Tasarım Soruları (read-only)

Tarih: 2026-05-01
Kapsam: backend mapping pipeline + agency/route DB içeriği + test surface'i. Sadece okuma; pytest/manage.py shell DML çalıştırılmadı (yalnız SELECT).

---

## Bölüm 1 — Agency tablosu içeriği

**Bulgu:** `gtfs_agency` tablosunda 9 satır var; "IETT" name'inde tek satır mevcut (`id=9`, `agency_id='1'`) — varyant yok. β filtresi için kritik değer: `agency_id = 9` (DB foreign key).

`apps/gtfs/models.py:46-57` Agency modeli:

```python
class Agency(TimestampedModel):
    agency_id = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=200)
    url = models.URLField()
    timezone = models.CharField(max_length=50, default="Europe/Istanbul")
    lang = models.CharField(max_length=10, default="tr")
```

İki ayrı identity field var: `id` (Django auto PK, integer) ve `agency_id` (GTFS feed'den gelen string). `Route.agency` ForeignKey'i `agency.id` (integer PK) üzerine bağlanır (`models.py:79`).

`SELECT id, agency_id, name FROM gtfs_agency ORDER BY id;` çıktısı (tam, 9 satır):

```
 id | agency_id |       name
----+-----------+-------------------
  1 | 6         | Şehirhatları A.Ş.
  2 | 4         | TCDD
  3 | 11        | Metro İstanbul
  4 | 37        | Minibus
  5 | 19        | Taksi Dolmus
  6 | 20        | IDO
  7 | 48        | Turyol
  8 | 33        | Dentur Avrasya
  9 | 1         | IETT
```

Spec §3.3'teki "Marmaray=2, Vapur=1" değerleri DB `id` kolonu ile eşleşiyor: Marmaray (TCDD operatörü) `id=2`, Vapur (Şehirhatları) `id=1`. β filtresinde İETT rotası için `agency_id = 9` kullanılacak.

---

## Bölüm 2 — short_name → Route PK kardinalitesi

**Bulgu:** Test edilen 4 İETT short_name'inde β filtresi (agency_id=9, route_type=3) sonrası HER short_name hâlâ 1'den fazla satır; minimum 7 (29B), maksimum 149 (AVR1) — yani β politikası 1:1 değil 1:N kalıyor, "ilk satır seç" deterministik bir tie-breaker (örn. `ORDER BY route_id ASC`) gerektiriyor.

Filtre öncesi kardinalite (`SELECT short_name, COUNT(*) AS row_count FROM gtfs_route WHERE short_name IN ('29B', '15B', '34BZ', 'AVR1', 'M2') GROUP BY short_name ORDER BY row_count DESC;`):

```
 short_name | row_count
------------+-----------
 AVR1       |       149
 15B        |        21
 34BZ       |        17
 29B        |         7
 M2         |         1
(5 rows)
```

β filtresi sonrası (`agency_id = 9 AND route_type = 3`):

```
 short_name | filtered_count
------------+----------------
 15B        |             21
 29B        |              7
 AVR1       |            149
 34BZ       |             17
(4 rows)
```

Dört bus short_name'inin tümü filtre sonrası DEĞİŞMEDİ — yani agency+type filtresi bu örnekler için indirgeyici değil. M2 metro olduğu için bus filtresine takıldı, çıktıda yok (filtre öncesi 1 satır → filtre sonrası 0 satır).

Sonuç: Yol B'de short_name → tek PK çözümü için ek tie-breaker şart. `ORDER BY route_id ASC LIMIT 1` deterministik; canonical varyant her zaman alfabetik en küçük route_id (örn. 29B → `iett:1562`, recon raporu Bölüm 1 ile tutarlı). Alternatif (`MIN(id)`) de deterministik ama route_id ile sıralama daha okunaklı.

---

## Bölüm 3 — Mapping cache JSON formatı genişletmesi

**Bulgu:** `build_mapping` 5 üst-seviye anahtarlı bir dict döndürüyor (`snapshot_date`, `snapshot_day_type`, `by_kapi`, `active_routes`, `routes_by_mode`); production tüketicileri yalnızca 2 dosya (`tasks.py:264-273`, `admin_views.py:88-99`) ve her ikisi de `.get("...")` ile defansif okuduğu için yeni `route_id_by_short_name` alanı eklemek geriye dönük uyumlu — eski snapshot crash atmaz, graceful skip yapar. enrich.py'nin imzası genişlemiyor; mevcut `mapping: dict` parametresine yeni alt-key okumayla yeterli.

`apps/realtime/mapping.py:155-164` `build_mapping` return shape:

```python
return {
    "snapshot_date": snapshot_date.isoformat(),
    "snapshot_day_type": snapshot_day_type,
    "by_kapi": dict(by_kapi),
    "active_routes": sorted(active_routes),
    "routes_by_mode": {
        "metrobus": metrobus_active,
        "bus": bus_active,
    },
}
```

Spec §5.7 ile uyum: `by_kapi` her KapiNo için sıralı interval listesi, her interval `{start_sec, end_sec, hat, guzergah}` (hat = SHATKODU = short_name).

**Tüketici grep'i** — production kodda `MAPPING_CACHE_KEY` veya `iett:mapping:current` okuyan yerler:

1. `apps/realtime/tasks.py:264` `raw_mapping = redis_client.get(MAPPING_CACHE_KEY)` → `tasks.py:273` `mapping = json.loads(raw_mapping)`. Sonra `enrich_with_route_id(vehicles, mapping)` (line 215). Mismatch detection için `mapping.get("snapshot_day_type")` (line 283).
2. `apps/realtime/admin_views.py:88-92` `raw_mapping = redis_client.get(MAPPING_CACHE_KEY)` → `mapping_payload = json.loads(raw_mapping)` → `mapping_payload.get("snapshot_date")`, `.get("snapshot_day_type")`.

Her iki tüketici de `.get(...)` ile spesifik anahtara erişir; iterate etmiyor. `route_id_by_short_name` yeni anahtarını eklemek mevcut tüketicileri etkilemez.

**Backward compat (eski snapshot + yeni kod)**: `enrich.py:55` zaten `by_kapi = mapping.get("by_kapi", {})` kullanıyor. Yeni kod `mapping.get("route_id_by_short_name", {})` ile okuyup boş dict alırsa, lookup miss → fallback davranışı tasarım kararı (None döndür ya da hat'ı geçici route_id olarak bırak; doğrulanamadı: bu fallback'ın hangi davranışı sergileyeceği kullanıcı tasarım kararı).

**enrich_with_route_id imzası**: `def enrich_with_route_id(vehicles, mapping: dict)` — imza genişlemiyor. enrich.py:89 satırı `route_id = intervals[idx]["hat"]` → yeni mantık `route_id = mapping.get("route_id_by_short_name", {}).get(intervals[idx]["hat"])` şeklinde tek satır değişikliği. Yeni helper gerekmiyor.

---

## Bölüm 4 — Test fixture'ları ve assertion'larının kapsamı

**Bulgu:** Üç dosyada toplam ~25 test var. enrich + integration testlerin neredeyse tamamı `route_id == "29B"` / `"15B"` / `"500T"` / `"34BZ"` / `"M2"` literal'ları üzerine kurulu — Yol B sonrası hat→PK çevrimi yapıldığında bunların hepsi mutlaka değişmeli (hem fixture mapping'e `route_id_by_short_name` eklenmeli, hem assertion expected değeri PK'ya dönmeli). mapping_build testi izole kalır çünkü `build_mapping` PK'yı bilmiyor; kırılmayan diğer alt-grup mapped/unmapped sayaç + defansif testler.

**`apps/realtime/tests/test_enrich.py`** (12+4 = 16 test) — fixture short_name değerleri `"29B"`, `"15B"`, `"500T"`. Asserlerin tipik şekli:

```python
def test_exact_match_inside_interval():
    mapping = _mapping(**{"A-231": [_interval(1000, 2000, "29B")]})
    vehicles = [_make_vehicle("A-231", 1500)]
    out = enrich_with_route_id(vehicles, mapping)
    assert out[0].route_id == "29B"
```

(test_enrich.py:92-96, aynı pattern: `_timestamp_equals_start_inclusive`, `_timestamp_equals_end_inclusive` line 99-110, `_overlap_picks_later_start` line 148-159 — `"15B"` bekler, `_overnight_continuation_uses_extended_seconds` line 194-206 → `"500T"`). Yol B sonrası bu 16 testten "match" kontu yapanların TÜMÜ değişmeli (≈ 9 test). Yalnız "unmapped" kontu yapanlar (`_timestamp_one_sec_after_end_unmapped`, `_kapi_not_in_mapping_unmapped`, `_empty_intervals_list_defensive`, `_corrupt_mapping_missing_by_kapi_key`, `_empty_vehicles_list`, `_input_vehicles_not_mutated` muhtelif) `assert out[0].route_id is None` kullandığı için kırılmaz — yaklaşık 6 test.

**`apps/realtime/tests/test_mapping_build.py`** (12 test) — `_gorev` fixture default `hat_kodu="15SK"` (line 34), test'lerde `"29B"`, `"15SK"`, `"34A"`, `"34BZ"`, `"500T"`, `"HA-3"`, `"M2288X"`. Fakat assertion'lar `out["active_routes"]` ve `out["routes_by_mode"]` üzerinde, yani **build_mapping'in outputu PK içermiyor; bu testler Yol B'de hiç değişmez** (build_mapping intervals'da `hat` field'ını korumalı). Yalnız build_mapping payload shape genişlerse (örn. `route_id_by_short_name` eklenirse) `test_build_empty` line 55-63 dict eşitlik kontrolü kırılır — 1 test.

**`apps/realtime/tests/test_fetch_task.py`** (~17 test) — `_seed_mapping` (line 163-181) hat literal'ları `"29B"`, `"34BZ"` üzerine kurulu. Snapshot içinde `route_id` field beklenen değerler:

```python
assert snapshot["vehicles"][0]["route_id"] == "29B"  # line 205
assert by_id["A-231"]["route_id"] == "29B"            # line 241
assert veh["route_id"] == "29B"                       # line 421
target = next(v for v in payload["vehicles"] if v["id"] == "A-100")
assert target["route_id"] == "29B"                    # line 562
```

Etkilenen test sayısı: en az 6 (happy_path, unmapped_vehicle_included, payload_format, mapped_count_excludes_unmapped, spatial_check_keeps_near_vehicle, spatial_check_skips_when_no_shape_cached). Etkilenmeyen: cache miss / adapter exception / empty fleet / unmapped_count overwrite / day-type mismatch counter / spatial nullifies far — bunlar `route_id is None` ya da counter assertion'ı yapıyor (~10 test).

**`apps/realtime/tests/test_integration.py`** (7 test) — End-to-end senaryoda dynamic route assignment fixture'ı (line 213-219):

```python
for kapi in kapis[0:4]:
    by_kapi[kapi] = [_interval(0, BIG_END_SEC, "29B")]
for kapi in kapis[4:7]:
    by_kapi[kapi] = [_interval(0, BIG_END_SEC, "34BZ")]
by_kapi[kapis[7]] = [_interval(0, BIG_END_SEC, "M2")]
```

Asserlerin (line 237-240, 351, 384-385, 410, 415, 498-501) hepsi `"29B"`/`"34BZ"`/`"M2"`/`"15B"` literal'larında — TÜM 4 senaryo (`test_end_to_end_chain_with_real_fleet_cassette`, `test_mapping_miss_then_present_recovery`, `test_same_kapi_different_routes_across_ticks`, `test_fetch_task_broadcast_reaches_websocket_consumer`) hem fixture hem assertion revize edilmeli. Yalnız `test_stale_cache_survives_adapter_failure` (line 266-305) `route_id` literal'ına bakmıyor; TTL ve byte-level identity test ediyor → kırılmaz.

**Toplam tahmini etki**: ~20 test'in route_id literal expected değeri PK'ya dönmeli + fixture mapping'lere `route_id_by_short_name` index eklenmeli. ~17 test (defansif/sayaç/unmapped/exception) hiç değişmez.
