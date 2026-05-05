# Pre-release audit — v1.0 öncesi son temizlik

**Tarih:** 2026-05-05
**Bağlam:** v0.8.0 → v0.9.0 KM-b zinciri tamam (4 tag basıldı: v0.8.1, v0.8.2, v0.8.3, v0.9.0; suite 312 + 219 = 531 yeşil). Bu rapor Yağız'ın istediği "lokalin son hali — eksiklik raporu" çıktısıdır. Hiç kod değişikliği yok; bulgular ham listelendi + "şu açık" / "şu temiz" değerlendirmesi yapıldı.

---

## 1. TODO/FIXME/XXX/HACK taraması

```
grep -rIn -E "(TODO|FIXME|XXX|HACK|PLACEHOLDER)" --include="*.py" --include="*.ts" --include="*.css" --include="*.md"
```

| Dosya:Satır | Tür | İçerik özeti | Değerlendirme |
|---|---|---|---|
| `backend/apps/realtime/adapters/iett_soap.py:169` | TODO (Phase 6) | Midnight-rollover edge case (vehicle 23:55 → 00:05 timestamp diff) | **Aktif borç**, dokümante kalır. v1.0+ backlog "real-time ETA" altına taşınabilir |
| `backend/apps/gtfs/views.py:80` | TODO(perf) | Faz 6 — büyük route'lar için query optimization | **Aktif borç**, gerçekleşmedi (Faz 6 v1.0+ backlog'a ertelendi). Yorum kalır |
| `frontend/src/styling/route_colors.ts:36/45/54/65/67` | TODO ×5 | T2/T3/Marmaray/F4/ferry/bus kurumsal renk doğrulaması | **Aktif borç**, İBB kurumsal kimlik dokümanı bekleniyor. Yorumlar kalır (kullanıcı PR açarsa rehber) |
| `backend/apps/gtfs/management/commands/download_gtfs.py:152` | (false-positive) | Yorum içinde `.tmp.dl-XXX.tmp` dosya isim deseni placeholder syntax | TODO/HACK değil, **dokunma** |
| `MINI_ISTANBUL_3D_SPEC.md:1062` | (false-positive) | Örnek error message `route_id 'XXX'` | Doc örnek, **dokunma** |
| `CLAUDE.md:63` | (meta) | "Yeni `.md` dosyası açma… `TODO.md` gibi" | Kural metni, **dokunma** |

**Sonuç:** 7 gerçek TODO, hepsi **bilinçli/aktif borç**. v1.0 öncesi blokeleyici yok.

---

## 2. Placeholder / TBD / commit hash placeholder

### ROADMAP.md

| Satır | İçerik | Durum |
|---|---|---|
| 869, 871, 897 | KM5-f / v0.8.0 release tag `<TBD>` | **AÇIK** — v0.8.0 tag'ı 2026-05-03'te basıldı, hash replace edilmemiş |
| 1068 | KM-c "(commit hash placeholder, 2026-05-04)" | **AÇIK** — v0.8.1 KM-c commit hash'i replace edilmemiş |
| 1072 | KM-d "(commit hash placeholder, 2026-05-04)" | **AÇIK** — v0.8.1 KM-d aynı |
| 1076 | KM-e "(commit hash placeholder, 2026-05-04, yayın blokeleyici)" | **AÇIK** — v0.8.1 KM-e aynı |
| 1087 | KM-f notu "ROADMAP commit hash placeholder'ları replace" | **YAPILACAK görev** — bu placeholder replace turu yapılmamış |

**Sonuç:** 5 placeholder güncellemesi ROADMAP'te bekliyor. v0.8.1 KM-f'in son adımı olarak Yağız'ın yapması gereken iş — `git log --oneline | grep <KM-c/d/e/5-f>` ile hash'leri çek, replace et. Uygulamadan önce Yağız onayı gerekir.

### Spec Ek A.19 borç tablosu güncellenmesi

Spec Ek A.19 tablosu **borç #1-#9** ile bitiyor (line 1858). v0.8.1 manuel smoke turu sonrası eklenmiş borçlar Spec'e işlenmemiş:

| Borç | Kaynak | Spec'te var mı |
|---|---|---|
| #11 "Denizde araç" | Yağız 2026-05-04 KM-d sonrası smoke | **Yok** (commit mesajlarında geçiyor) |
| #12 "Hiçbiri sonrası bus görünüyor" | KM-g araştırma 2026-05-05 | **Yok** |
| #13 "Hayalet leke" | KM-g | **Yok** |
| #14 "Reset semantik tutarsızlığı" | KM-g | **Yok** |
| #15 "Aktif hat panelde belirgin değil" | KM-h.1 | **Yok** |
| #16 "Fokuslu polyline yeterince güçlü değil" | KM-h.2 | **Yok** |
| #17 "M7 scheduled simulasyon eksik (GTFS data)" | KM-h.3 | **Yok**, v1.0+ backlog (data quality) |

Kapatılan borçlar:
- #1, #6, #7, #11/#12/#13/#14, #15/#16 → kapatıldı (commit'ler mevcut)
- #2 → 🟡 "kanıt-bekleniyor 2026-05-05 04:01 UTC" — **bugün 2026-05-05**, pencere geçti, doğrulama yapılabilir
- #3, #5, #8 → kapatıldı
- #4 → kapatıldı (vendor split, total bundle aynı kaldı; commit mesajında neden açıklandı)
- #9 → kapatıldı
- #17 → tanı tamam, fix v1.0+ backlog (GTFS feed data quality)

**Sonuç:** Spec Ek A.19 manuel update bekliyor — borç #11-#17 envantere işlenmeli (Yağız tarafı, "Yağız sonradan ekler" diye not bıraktım her commit'te).

### KM-b beat schedule doğrulama

ROADMAP'te `KM-b 🟡` durumunda; 2026-05-05 04:01 UTC penceresi bugünün TR sabahında geçti. Yağız'ın `last_run_at` sorgusu yapması gerekir (`SELECT name, last_run_at, total_run_count FROM django_celery_beat_periodictask WHERE name='refresh-iett-mapping';`). Kanıt sonrası ROADMAP'te ✅ işaretlenip v0.8.1 final tag basılır.

---

## 3. Beklenmedik dosyalar

```
git ls-files | grep -iE "(\.bak$|\.old$|_eski|_old$|__pycache__)"
```

**Sonuç:** 0 match ✓. Repo temiz.

`find` taraması da temiz (venv/node_modules dışında `.bak`/`.old` yok).

---

## 4. README durumu

**Yok.** Repo kökünde `README.md` mevcut değil. v0.9.0 KM-c kapsamı (sıfırdan yazılacak: hero ekran görüntüsü, ne yapar, niye yapıldı, mimari özet, kurulum, demo URL, lisans, teşekkürler).

GitHub repo public yapılmadan önce kritik. KM-c sırasında ele alınır.

---

## 5. Test kapsamı dışı modüller

### Frontend (`frontend/src/`)

| Dosya | Durum | Değerlendirme |
|---|---|---|
| `main.ts` | Entry point, MapLibre side-effect orchestration | **Test edilmesi pratik değil** (browser-bound, kapsamlı E2E gerekir) |
| `data/api.ts` | HTTP fetch wrapper | Pure'a yakın, **test eklenebilir** ama düşük getiri |
| `data/websocket.ts` | WebSocket connect + reconnect logic | **Test eklenebilir**, ama mock infrastructure maliyetli |
| `render/buildings_layer.ts` | MapLibre layer config | Sadece map.addLayer çağrısı, test'i map mock gerektirir |
| `render/terrain.ts` | MapLibre terrain config | Aynı |
| `simulation/interpolator.ts` | Pure lerp util | **Test EKSIK** — basit, eklenebilir (5-10 satır) |
| `ui/last_update_indicator.ts` | DOM widget | Test eklenebilir, route_panel pattern'iyle |

**Sonuç:** Pure mantık (interpolator) için test eksik, **5-10 satırlık eklenebilir**. Diğerleri E2E gerektirir veya düşük getiri. v1.0 öncesi blokeleyici değil.

### Backend (`backend/apps/`)

Find komutu test_*.py hariç tutuyor; gerçek test'ler `apps/realtime/tests/` ve `apps/gtfs/tests/` altında dağılmış olabilir. Test sayısı **219** (175 realtime + 44 gtfs) → kapsamlı. Detaylı per-modül kapsama analizi v1.0+ Faz 7 KM6 (E2E + coverage report) kapsamında.

---

## 6. Spec Ek A.19 borç durumu — özet matris

| # | Borç | v0.x | Commit | Durum |
|---|---|---|---|---|
| 1 | route-lines line-width interpolate | v0.8.1 KM-a | `5b5007e` | ✅ |
| 2 | Beat schedule doğrulama | v0.8.1 KM-b | (sorgu Yağız) | 🟡 pencere geçti, doğrula |
| 3 | Mojibake popup uyarısı | v0.8.1 KM-c.1 | (placeholder) | ✅ |
| 4 | Bundle size > 500KB | v0.8.2 KM-a | `510d108` | ✅ vendor split (total aynı, neden commit mesajında) |
| 5 | URL persistence | v0.8.2 KM-b | `9745cc2` | ✅ |
| 6 | Vapur dblclick sessiz | v0.8.1 KM-d | (placeholder) | ✅ |
| 7 | Reset state corruption | v0.8.1 KM-e | (placeholder) | ✅ |
| 8 | Metrobüs popup label | v0.8.1 KM-c.2 | (placeholder, KM-c atomik) | ✅ |
| 9 | Metrobüs nokta görsel zayıf | v0.8.2 KM-c | `0311c4d` | ✅ |
| 11 | Denizde araç | v1.0+ backlog | — | 🟡 Yağız 2026-05-04 ek bulgu, Spec'te yok |
| 12 | Hiçbiri sonrası bus görünüyor | v0.8.1 KM-g | `c1a21a4` | ✅ |
| 13 | Hayalet leke | v0.8.1 KM-g | `c1a21a4` | ✅ |
| 14 | Reset semantik tutarsızlığı | v0.8.1 KM-g | `c1a21a4` | ✅ kapsam genişlemesi |
| 15 | Panel focus highlight yok | v0.8.1 KM-h.1 | `ac77a52` | ✅ |
| 16 | Fokuslu polyline zayıf | v0.8.1 KM-h.2 | `ac77a52` | ✅ |
| 17 | M7 scheduled eksik | v1.0+ backlog | `ac77a52` (tanı) | 🟡 GTFS feed data quality, fix v1.0+ |

**Açık 3 madde:**
1. **#2 KM-b** — beat schedule doğrulama (bugün yapılabilir)
2. **#11** — denizde araç (v1.0+ backlog)
3. **#17** — M7 GTFS data (v1.0+ backlog)

Yayın için blokeleyici yok.

---

## 7. v1.0 öncesi atlanmış bir şey var mı?

ROADMAP Faz 7 sürüm zinciri:
- v0.8.1 ✅ (KM-a..h, tag basıldı)
- v0.8.2 ✅ (KM-a..c, tag basıldı)
- v0.8.3 ✅ (KM-a, KM-b, tag basıldı)
- v0.9.0 → KM-a ✅, KM-b ✅, **KM-c (README), KM-d (CONTRIBUTING), KM-e (repo metadata), KM-f (tag) açık**
- v0.9.1 → tamamı açık (production deployment, 2-3 gün)
- v1.0.0 → yayın günü

**v1.0 öncesi yapılacak (v0.9.0 + v0.9.1):**
- README (KM-c)
- CONTRIBUTING (KM-d)
- Repo metadata + topics (KM-e, GitHub UI)
- Production: PostgreSQL+PostGIS+Redis sunucu kurulum, systemd ×4, Nginx vhost, SSL, rate limiting, backup cron
- Smoke (mobil + masaüstü + Cloudflare WARP)

**Hiçbir şey atlanmadı.** Yayın sürüm zinciri planlı.

---

## 8. Yorum hijyen ön-tarama (ADIM 2 için)

İç-referans kalıbı taraması:
- `KM5-` (Faz 5.5 alt-tur referansları): backend ve frontend yorumlarda yoğun
- `Spec Ek A.\d+`: backend yorumlarda var, frontend daha az
- `Yağız 2026-..`: birkaç frontend dosyasında
- `f-polish-\d`: frontend KM1 alt-iş referansları
- `Borç #\d+` / `borç #\d+`: KM-c sonrası eklenenlerde

ADIM 2'de dosya dosya sadeleştirilecek. Aktif risk yorumları (`IETT_BUS_MAPPING_ENABLED=False — hibernation`, `mapping retire — vehicle.route_id null çoğunlukla`) sürüm referansı temizlenmiş haliyle kalır.

---

## 9. Genel değerlendirme

**TEMİZ:**
- Repo'da `.bak/.old/_eski` yok ✓
- Hardcoded secret yok (KM-a audit'i)
- Tracked `.env` yok ✓
- Beklenmedik tracked dosya yok ✓
- Tüm sürümler tag'lı, suite 531/531 yeşil ✓

**AÇIK (Yağız aksiyon):**
1. ROADMAP commit hash placeholder ×5 (v0.8.0 release tag, KM5-f, v0.8.1 KM-c/d/e) — `git log` çek, replace
2. Spec Ek A.19 manuel update — borç #11-#17 envantere işlenmeli
3. KM-b beat schedule doğrulama (bugün penceresi geçti, sorgu hazır)

**AÇIK (yapılacak iş):**
1. v0.9.0 KM-c README sıfırdan
2. v0.9.0 KM-d CONTRIBUTING
3. v0.9.0 KM-e repo metadata
4. v0.9.0 KM-f tag v0.9.0
5. v0.9.1 production deployment (2-3 gün)
6. v1.0.0 yayın

**OPSİYONEL ADIM 2:**
- Yorum sadeleştirme (Mini Tokyo 3D stili)
- `simulation/interpolator.ts` için 5-10 satırlık birim test eklenebilir (düşük getiri, atlanabilir)
