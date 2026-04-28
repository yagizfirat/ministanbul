# CLAUDE.md

## Project-Specific Guidelines (Mini Istanbul 3D)

Bu bölüm projeye özeldir. Aşağıdaki Karpathy kuralları genel davranış rehberidir; çakışma olursa **bu bölüm önceliklidir**.

### Stack ve ortam

- **Backend:** Python 3.11+, Django 5.1 + DRF + drf-gis + django-filter, GeoDjango (PostGIS 3.6), Celery 5.x + django-celery-beat, Redis 7 (Windows'ta Memurai, port 6379).
- **Frontend (Faz 4+):** Vite + TypeScript, MapLibre GL JS 5.x, Three.js (custom layer), deck.gl.
- **Veritabanı:** PostgreSQL 15 + PostGIS 3.6. Bağlantı bilgileri `.env`'de; GeoDjango için `GDAL_LIBRARY_PATH` / `GEOS_LIBRARY_PATH` Windows bundle yollarından okunur.
- **Native Windows kurulumu — Docker/WSL yok.** Shell olarak Git Bash kullanılır (Unix syntax, forward slash). Sanal ortam `backend/venv/Scripts/activate`. Memurai Windows servisi olarak çalışır.
- **Port haritası:** Django HTTP `8010`, Daphne ASGI `8011` (Faz 3+), Vite dev `5173` (Faz 4+). Diğer projeler 8000/8001'de — bu portları kullanma.

### İETT rate-limit kuralları (kritik — ihlal edilemez)

İETT SOAP API'si için ampirik olarak ölçülmüş limitler:

| Parametre | Değer |
|---|---|
| Sliding window | ~40 dakika |
| Pencere kapasitesi | ~72 çağrı |
| Cooldown | ~30 dakika |
| Backend refresh rate | ~60 saniye |

**Kurallar:**

- **Canlı API çağrısı yasak — Yağız'ın açık onayı olmadan asla.** Geliştirme ve test sırasında `apps/realtime/tests/cassettes/` altındaki kayıtlı yanıtlar kullanılır (cassette replay disiplini). Yeni cassette eklemek için bile önce sor.
- **Birden fazla geliştirici aynı IP/anahtarı paylaşıyor olabilir.** Test koşusu `requests` ile gerçek endpoint'e gitmemeli; `fakeredis` + cassette + monkeypatch zincirini kıracak değişiklikten kaçın.
- **`SlidingWindowLimiter` ve distributed lock** üretimde load-bearing — bunları "test kolaylığı için" bypass etme. `record_call()` sadece 2xx yanıt sonrası tetiklenir; bu davranışı koru.
- **Smoke test sadece Yağız onayıyla, kontrollü, tek/çift çağrı.** Sonuç (rate budget yüzdesi dahil) ROADMAP'e yazılır.

### Raporlama dili ve biçimi

- **Tüm raporlar, açıklamalar, plan özetleri Türkçe.** Yağız Türkçe çalışıyor (auto-memory: `user_profile`).
- Kod, kod yorumları, log mesajları, test isimleri **İngilizce** kalır (zaten codebase böyle).
- **Her faz/adım sonunda dur, somut çıktı göster.** "Yapıldı" demek yetmez; commit hash, test sayısı, ölçüm, dosya yolu — ne uygulanabiliyorsa o (auto-memory: `feedback_step_by_step`). Birkaç adımı arka arkaya sessizce yürütme.
- **Commit mesajları conventional-commit, sade.** Co-Authored-By trailer'ı yok, Claude imzası yok (auto-memory: `feedback_commit_messages`). Format: `feat(realtime): …`, `fix(gtfs): …`, `docs(roadmap): …`, `chore: …`.

### Dosya yapısı kuralları

```
mini-istanbul/
├── backend/
│   ├── config/                  Django settings (base/development/production)
│   ├── apps/
│   │   ├── core/                Ortak yardımcılar, sabitler
│   │   ├── gtfs/                Statik GTFS modelleri + import komutları
│   │   └── realtime/            Canlı veri (adapter, parser, task, mapping, enrich, calendar, admin)
│   ├── templates/               Sadece preview/admin için server-render HTML
│   └── requirements/            base.txt + development.txt + production.txt
├── data/gtfs/                   İBB feed'leri (git-ignored)
├── _backups/                    pg_dump yedekleri (git-ignored)
├── frontend/                    Vite/TS projesi (Faz 4'te kurulacak)
├── ROADMAP.md                   Faz/adım bazlı yol haritası — her oturumda ilk okunacak
├── MINI_ISTANBUL_3D_SPEC.md     Teknik referans (büyük dosya — gerekli bölümü hedefli oku)
└── CLAUDE.md                    Bu dosya
```

- **Yeni Django app `apps/` altına.** Üstte serpiştirme.
- **`_research/`, `scratch/` gibi tek seferlik analiz scriptleri:** kullanıldıktan sonra silinir, sonuç ROADMAP/SPEC'e yazılır (örnek: 5b-ii alignment script silindi).
- **ROADMAP.md her adım sonunda güncellenir** — durum, commit hash, ampirik ölçüm. SPEC'e ek bulgular Ek A'ya işlenir.
- **Yeni `.md` dosyası açma** (özellikle `NOTES.md`, `TODO.md`, `PLAN.md` gibi). Bağlam ROADMAP/SPEC'te toplanır.
- **`requirements/base.txt`'e paket eklerken:** versiyon aralığı (`>=X,<Y`) yaz, dondurma yapma — `development.txt`/`production.txt` üst katmanda gerekirse pinler.

---

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.
