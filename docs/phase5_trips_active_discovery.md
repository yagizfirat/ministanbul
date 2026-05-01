# Faz 5 — `/api/trips/active/` Keşif Raporu

**Tarih:** 2026-05-01 (Cuma)
**Komut:** `backend/_research_phase5.py` standalone script (`PYTHONIOENCODING=utf-8 venv/Scripts/python.exe _research_phase5.py`). Script, Django setup + ORM sorguları + `data/gtfs/public/calendar.csv` ham parse içeriyor; rapor commit'inden sonra silindi.
**Kapsam:** Sadece `route_id LIKE 'public:%'` (Faz 5 hedefi metro/Marmaray/vapur). İETT feed'i (3-haneli otobüs hatları) Faz 4'te canlı veri yoluyla işleniyor, bu raporun dışında.

---

## 1. Genel envanter

| Metrik | Değer |
|---|---|
| Public Route | **498** |
| Public Trip | **14 387** |
| Public StopTime | **199 969** |

**Mod dağılımı (route_type → trip / route / distinct service_id):**

| rt | İsim | Trip | Route | Service |
|---:|---|---:|---:|---:|
| 0 | tram | 2 498 | 3 | 5 |
| 1 | subway | **8 001** | 15 | 12 |
| 4 | ferry | 2 373 | **100** | 28 |
| 6 | aerial | 4 | 2 | 1 |
| 7 | funicular | 401 | 3 | 6 |
| 9 | (extended) | 880 | 317 | 7 |
| 10 | (extended) | 230 | 58 | 2 |

`route_type=9` ve `10` GTFS basic spec'in dışında (Route modelindeki `ROUTE_TYPE_CHOICES` 0-7 tanımlı; 5 yok, 8 yok, 9 yok, 10 yok). `Route.route_type = IntegerField(choices=...)` `choices` validator yalnız form tarafında çalıştığı için bu kayıtlar geçti. Faz 5 hedefi (`metro/marmaray/ferry`) `rt ∈ {1, 4}` ile karşılanır; `rt=9/10` hatları endpoint'e dahil edilmemeli (bilinmeyen taşıma türü).

→ **Sonuç:** Endpoint `mode` parametresi `subway/ferry/tram/funicular` whitelist üzerinden çalışacak (`MODE_TO_ROUTE_TYPE` mevcut backend mapping'i ile uyumlu); `rt=9/10` 880+230 trip dahil edilmiyor, ileride GTFS extended kod araştırması ayrı iş.

---

## 2. StopTime boyutu

200 K satır toplam StopTime; Trip başına ortalamalar:

| rt | İsim | Trip örnek | avg/trip | min | max |
|---:|---|---:|---:|---:|---:|
| 0 | tram | 2 498 | 25.0 | 10 | 31 |
| 1 | subway | 4 999 | 14.8 | 5 | 43 |
| 4 | ferry | 2 368 | **2.6** | 2 | 12 |
| 6 | aerial | 4 | 2.0 | 2 | 2 |
| 7 | funicular | 400 | 2.0 | 2 | 2 |
| 9 | (ext) | 880 | 34.4 | 3 | 83 |
| 10 | (ext) | 230 | 2.0 | 2 | 4 |

Kompozit index `st_trip_seq_idx` (`trip_id, stop_sequence`) Faz 1'de zaten kuruldu (models.py:151). Ferry ve funicular ortalama 2 stop (origin-destination), aralıkta interpolasyon polyline takip edecek.

→ **Sonuç:** "Bu trip şu an aktif mi?" sorgusu, trip başına `MIN(arrival_time)` ve `MAX(arrival_time)` aggregation ile çözülebilir. Subway trip'i ortalama 15 stop × 8001 trip = 120 K subway StopTime — `mode=subway` filtresi sonrası `JOIN trips ON route + GROUP BY trip` PostgreSQL'de subseconds bekleniyor (cache ihtiyacı yok, bunu KM ölçeceğiz).

---

## 3. Zaman davranışı

| Alan | Bulgu |
|---|---|
| `arrival_time` Django field | **`DurationField`** (Postgres `interval`) |
| Python tipi | `datetime.timedelta` |
| Maks. gözlem | `timedelta(days=1, seconds=4087)` = **25 h 14 m** (90 487 sn) |
| `arrival_time ≥ 24h` satır sayısı | **1 685** |

GTFS spec'inin `25:30:00` overnight format'ı `DurationField` ile sorunsuz saklanıyor — tahmin edildiği gibi string parse'a gerek yok, ORM doğrudan `timedelta` döner. PostgreSQL TIME limiti (`24:00:00` reddi) bu modelde sorun yaratmıyor çünkü TIME değil INTERVAL kullanılıyor.

5 örnek trip:

```
trip=3071264   ferry    first=19:25:00  last=19:50:00  (2 stops)
trip=949118    subway   first=09:51:00  last=10:13:04  (13 stops)
trip=954198    tram     first=06:00:00  last=07:08:08  (31 stops)  ← T1 ekstra duraklı
trip=3104112   subway   first=22:40:15  last=23:13:00  (18 stops)
trip=910473    subway   first=15:24:00  last=15:53:05  (14 stops)
```

→ **Sonuç:** Endpoint'in "şimdi" sorgusu `now_secs = h*3600 + m*60 + s` integer karşılaştırmasıyla `WHERE first_arr ≤ now_secs AND last_arr ≥ now_secs` yapacak. **Overnight handling:** Bugünün gece yarısından sonraki sefer iki yerden gelebilir — (a) bugünkü `service_id`'ler için `arrival_time ≥ 24h` kayıtları `now + 86400` olarak değerlendirilmeli, (b) dünün `service_id`'leri için `arrival_time` aralığı ileri taşınarak. KM2/KM3 simulasyon adımında karar — endpoint v0 için "today's trip × first ≤ now ≤ last" yeterli, gece yarısı blackout kabul.

---

## 4. Service / Calendar davranışı — **EN KRİTİK BULGU**

### 4.1 Calendar tablosu Django modelinde **YOK**

`apps/gtfs/models.py` içinde `Calendar` veya `CalendarDate` modeli **tanımlı değil**. `import_gtfs.py:54` `calendar.csv`'yi `REQUIRED_CSVS`'e koyuyor ve `pandas.read_csv` ile okuyor (`feed["calendar"]` DataFrame'e yüklüyor) — ama `_load_feed` içinde **hiçbir yerde tüketilmiyor**:

```bash
$ grep -n "feed\[" apps/gtfs/management/commands/import_gtfs.py
# feed["agency"], feed["routes"], feed["stops"], feed["shapes"],
# feed["trips"], feed["stop_times"], feed["frequencies"]
# feed["calendar"] — YOK
```

`Trip.service_id` sadece `CharField(db_index=True)` — değer mevcut, bağıntı yok.

→ **Sonuç:** Faz 5 KM1'in ilk işi: `Calendar` ve `CalendarDate` Django modelleri + `import_gtfs.py`'a yükleme adımı + migration. Aksi halde "bugün hangi servis aktif" sorusu CSV'ye runtime'da gitmek zorunda — kabul edilemez.

### 4.2 Public feed `end_date` zaten dolmuş

`data/gtfs/public/calendar.csv` (49 satır):

| Alan | Min | Max |
|---|---|---|
| `start_date` | 20180801 | 20221231 |
| `end_date` | 20190303 | **20241231** |

Bugün **2026-05-01**. Tüm 49 servis tarih aralığı dışında.

```
2026-05-01 (FRIDAY) için:
  friday=1 AND in-range:  0 servis
  friday=1 ama tarih dışı: 24 servis
```

`calendar_dates.csv` public feed'de **yok** (sadece `agency, calendar, frequencies, routes, shapes, stop_times, stops, trips`). Yani exception override mekanizması da yok.

→ **Sonuç:** Endpoint v0 için iki yol var, **proje kararı gerekiyor:**
  - **(a) Tarih filtresini bypass et:** Bugünün haftagününe `monday/tuesday/.../sunday=1` yeterli; `start_date/end_date` ignore. Geliştirme/demo için anında çalışır.
  - **(b) Public feed güncelle:** İBB Açık Veri portalında daha yeni sürüm var mı kontrol — yoksa (a) zorunlu.
  - **(c) Hibrit:** `start_date/end_date` esnetilmiş clamp (örn. `end_date < today` ise feed yıllık tekrarlıyor varsay).

İlk sürüm (a) ile ilerlemek pragmatik; ROADMAP'a "Public feed yenileme — Faz 5 Risk" notu düşülecek.

### 4.3 Trip ↔ Calendar service_id eşleşmesi

| Metrik | Değer |
|---|---|
| Distinct `service_id` Trip'te | **49** |
| Distinct `service_id` calendar.csv'de | **49** |
| Kesişim | **49** |
| Trip'te orphan service_id | 0 |

Birebir eşleşme — orphan yok. Calendar import edildiğinde FK güvenle kurulabilir (ama opsiyonel; mevcut `service_id CharField` zaten yeterli).

Örnek service_id `108`: `mon=1 tue=1 wed=1 thu=1 fri=1 sat=1 sun=0 start=20221231 end=20241231` — haftaiçi+Cumartesi servisi (Pazar dışında her gün).

→ **Sonuç:** Calendar modelini `service_id`'yi PK yapıp Trip ile FK kurmak temiz; ama Faz 5 v0 için skipping mümkün — `service_id LIKE` ile iki tablo `JOIN ... ON trip.service_id = calendar.service_id` zaten çalışır.

---

## 5. M2 Sanity (Yenikapı ↔ Hacıosman) ✅

```
route_id   = 'public:1298'
short_name = 'M2'
long_name  = 'YENİKAPI - HACIOSMAN'
route_type = 1 (subway)
```

**Trip dağılımı:** 1 368 toplam (dir=0 → **673**, dir=1 → **695**).

`direction_id=0` örnek trip `3104360` (`headsign='HACIOSMAN'`, `service_id=310`):

```
seq= 1  Yenikapı                       arr=05:40:00
seq= 2  Vezneciler - İstanbul Ü.       arr=05:42:04
seq= 3  Haliç                          arr=05:44:03
seq= 4  Şişhane                        arr=05:45:26
seq= 5  Taksim                         arr=05:47:47
   ...
seq=11  Sanayi Mahallesi               arr=06:00:00
seq=12  İTÜ - Ayazağa                  arr=06:03:11
seq=13  Atatürk Oto Sanayi             arr=06:05:14
seq=14  Darüşşafaka                    arr=06:07:13
seq=15  Hacıosman                      arr=06:09:05
```

Toplam 15 stop, sefer 29 dakika. Yön doğru: `direction_id=0` Yenikapı → Hacıosman (kuzey). `Vezneciler - İstanbul Ü.` kombo durak feed'de tek satır olduğu için 16 değil 15 stop görünüyor (gerçek M2'de 16 istasyon var, biri kombine edilmiş — feed seçimi).

→ **Sonuç:** `direction_id` sözleşmesi şuradan teyit: dir=0 başlangıç istasyonundan (`route.long_name` LHS), dir=1 sondan başa. Endpoint response'unda `direction_id` aynen geçirilecek; client polyline takibinde `polyline` (forward) + `polyline.reversed()` (Faz 5 ileri adım) ayrımı buradan sürüyor.

---

## 6. Shape coverage

| Metrik | Değer |
|---|---|
| Trip with shape (FK doldu) | **14 387 / 14 387 (%100)** |
| Trip without shape | 0 |

Faz 3 6h'de "public feed shape cache 496/496" raporlanmıştı (496 distinct shape). Şimdi trip-bazında: 14 387 trip aynı 496 shape'i paylaşıyor (çoklu trip → tek shape FK). Hiçbir trip shape'siz değil.

→ **Sonuç:** Endpoint response'u `shape_id` ya da inline polyline (`/api/routes/{id}/shape/` mevcut endpoint kontrat) emniyetle dönebilir, fallback yolu gerekmez. Frontend `simulation/polyline.ts` her trip için garantili polyline buluyor.

---

## Özet — endpoint tasarımına etkisi

| Bulgu | Tasarım kararı |
|---|---|
| Calendar/CalendarDate Django modeli yok | **Faz 5 KM1 zorunlu işi:** modeller + import + migration |
| Public feed `end_date=20241231` (geçmiş) | v0'da tarih filtresi bypass; ROADMAP'a "feed yenileme" risk notu |
| `arrival_time = DurationField` (timedelta) | String parse yok; integer-second karşılaştırma `total_seconds()` üzerinden |
| Overnight 1685 satır ≥ 24h | v0 "today × first ≤ now ≤ last" yeterli; cross-midnight v1+ |
| `route_type` 9 ve 10 (extended) | Endpoint whitelist: `subway/ferry/tram/funicular` (`rt ∈ {0, 1, 4, 7}`) |
| 200 K StopTime, 8 K subway trip | `min/max(arrival_time) GROUP BY trip` direkt SQL — cache yok |
| Shape FK %100 dolu | Polyline fallback yok; response'a `shape_id` veya inline geometry |
| Trip ↔ service_id 49/49 birebir | Calendar import edildiğinde FK kuruluşu temiz |
| M2 yön sözleşmesi: dir=0 = LHS→RHS | Endpoint `direction_id` aynen geçirir; reverse Faz 5 simülasyon adımı |

**Sırada (yeni mesajda birlikte tartışılacak):**
1. Calendar/CalendarDate model + import — KM1 mi yoksa endpoint'e gömülü kerteriz mi?
2. `end_date` bypass stratejisi — flag mi, ayar mı, hard-coded mu?
3. Endpoint response şeması — flat trip listesi mi, route bazında gruplanmış mı?
4. v0 kapsamına `mode=subway` mi yoksa hepsi mi?
