# Mini Istanbul 3D — Antigravity Kickoff Prompt

> Bu dosyayı Antigravity'de yeni bir sohbet/task başlatırken agent'a ilk mesaj olarak yapıştır.
> Agent dokümanı okuduktan sonra Faz 1'e başlayacak.

---

# 🎯 GÖREV

İstanbul'un toplu taşıma ağını gerçek zamanlı 3D olarak görselleştiren bir web uygulaması geliştireceksin. Bu proje tamamen planlanmış durumda — teknik spesifikasyonu proje kökündeki `MINI_ISTANBUL_3D_SPEC.md` dosyasında. **Bu dosya senin tek referans kaynağın.** Okuyacağın ilk dosya bu.

## İlk adımda yapacakların (sırayla)

1. `MINI_ISTANBUL_3D_SPEC.md` dosyasını oku, **tamamen** — hızlı tarama yeterli değil
2. Aşağıdaki "Mevcut Durum" bölümünü dikkate al — bazı kurulum adımları zaten yapıldı
3. "Çalışma Kuralları" bölümünü oku, bu kurallara uy
4. Faz 1'in çıktılarına bak (dokümanın Bölüm 7'sinde) ve **implementasyon planını sun bana**, onay bekle
5. Onay alınca Faz 1'i implement etmeye başla

---

# 📊 MEVCUT DURUM (ÖNEMLİ — tekrar kurma)

Geliştirici (Yağız) aşağıdaki adımları manuel olarak zaten tamamladı. **Bu bileşenleri yeniden kurmaya kalkma.**

## ✅ Zaten hazır olanlar

**İşletim sistemi:** Windows 11 (version 10.0.26200.8246)

**Python 3.11.11:** Kurulu, Conda altında (`C:\ProgramData\miniconda3`). Bazı paketler global kurulu olabilir — proje için **mutlaka ayrı venv** oluştur.

**Node.js 24.13.1:** Kurulu. Dokümanda 20 LTS yazıyor ama 24 de çalışır.

**Git 2.50:** Kurulu.

**PostgreSQL 15.15:** Kurulu, servis olarak çalışıyor (`postgresql-x64-15`).
- Postgres super-user şifresi: geliştirici ile konuş, `.env`'ye koymayacak
- Port: 5432 (varsayılan)

**PostGIS 3.6.2:** Kurulu, `mini_istanbul_dev` database'inde aktif edilmiş.

**Proje veritabanı kuruldu:**
- DB adı: `mini_istanbul_dev`
- User: `mini_istanbul_user`
- Şifre: `mini_istanbul_dev_pass` (geliştirme için, .env'de olacak)
- Extensions: `postgis`, `postgis_topology` aktif
- Bağlantı testi: `psql -U mini_istanbul_user -d mini_istanbul_dev` çalışıyor

**WSL2 + Ubuntu:** Kurulu ama kullanmayacağız (sadece bilgi için)

## ⚠️ Henüz eksik olanlar

**Redis:** Hiçbir yerde kurulu değil. Memurai Developer Edition kurulması gerekiyor. Winget ile:
```cmd
winget install MemuraiDeveloper
```
Bu Windows servisi olarak kurulur, 6379'da dinler, bilgisayar açıldığında otomatik başlar. Agent, Faz 2'ye (canlı veri) gelmeden önce bu kurulumu kullanıcıdan isteyecek.

**Django projesi:** Hiç oluşturulmadı. Senin ilk işin bu.

**Frontend:** Hiç oluşturulmadı. Faz 4'te.

---

# 🔍 ÖNEMLİ AMPİRİK BULGULAR

Planlama aşamasında İETT SOAP servisine 3 ayrı test yaptık. Sonuçlar dokümanın 4.2.1 bölümünde detaylı, kısaca:

- **Rate limit:** ~40 dakikalık sliding window, ~72 çağrı hakkı. İhlalde ~30 dakika cooldown.
- **Backend refresh rate:** Ortalama 60.3 saniye (yani daha sık çağrı yapmak boşa)
- **Authentication:** Servis anonim açık, CKAN token SOAP'ta etkisiz
- **Endpoint:** `https://api.ibb.gov.tr/iett/FiloDurum/SeferGerceklesme.asmx`
- **Metod (en önemli):** `GetFiloAracKonum_json()` — tüm filoyu (~6900 araç) tek çağrıda döndürüyor
- **Önemli uyarı:** WSDL bozuk, `zeep` kütüphanesi strict modda parse edemiyor. Ham HTTP POST kullan.

Test scriptleri proje kökünde mevcut (test_ibb_token_v2.py, test_rate_limit.py, test_refresh_rate.py, test_29b_tracking.py) — referans olarak bak.

**Strateji:** 60 saniyede bir çağrı + client-side interpolation. Alternatifleri tartışma, bu kararlaştırıldı.

---

# 🎨 ÇALIŞMA KURALLARI

## Nasıl ilerleyeceksin

1. **Her faz başlamadan önce plan sun, onay al.** "Faz 1'e başlıyorum" deme, "Faz 1 için şu 8 adımı sırasıyla yapacağım, onaylar mısın?" de. Plan onaylanınca başla.

2. **Her adımda kontrol noktası.** Bir dosya oluşturdun, bir migration çalıştırdın, bir testi geçtin — bunları geliştiriciye bildirerek ilerle. Sessizce 20 dosya oluşturma.

3. **Varsayım yapma, sor.** Dokümanda belirsiz bir şey varsa veya kararsızsan dur, geliştiriciye sor. "Ben tahmin ediyorum ki..." diye ilerleme.

4. **Her fazın "Bitiş Kriteri" var** (dokümanın Bölüm 7'sinde). O kriter karşılanmadan bir sonraki faza geçme. Geliştiriciye "Bitiş kriteri şu: X. Test et, doğru mu?" diye sor.

## Kod kalitesi

- **Type hints Python'da zorunlu.** Tüm fonksiyonlarda parametre + dönüş tipi.
- **Docstring kısa ama anlamlı.** "Bu fonksiyon X yapar" yeterli, ama yaz.
- **Test yazmadan commit etme.** Her yeni modül için pytest dosyası.
- **Magic number yok.** Örnek: `60` yazma, `IETT_FETCH_INTERVAL_SECONDS = 60` yaz.
- **`ruff` ve `black` kullan.** Format sorunları ilerde zaman kaybı yaratır.

## Bağımlılık yönetimi

- **Yeni paket eklemeden önce gerekçelendir.** "Şu şu yüzden X paketi gerekli, Django'nun yerleşik özelliği yetmiyor çünkü Y."
- **Exact version pin kullan.** `djangorestframework==3.15.2` yaz, `~=3.15` yazma.
- **Bağımlılıkları 3 dosyada tut:**
  - `requirements/base.txt` — prod ve dev'in ortak kullandığı
  - `requirements/dev.txt` — sadece geliştirme (pytest, ruff, ipython)
  - `requirements/production.txt` — sadece prod (gunicorn, sentry)

## Veritabanı kuralları

- **Model değişikliği = migration.** Hiçbir zaman "tabloyu elle oluşturdum" yapma.
- **Migration'lar reversible olsun.** `RunPython` kullanıyorsan `reverse_code` da yaz.
- **PostGIS field'larında SRID 4326 kullan.** Tüm geometriler WGS84.
- **Index'leri unutma.** `stop_times` tablosunda milyonlarca satır olacak, sorgulanan kolonlarda index mutlaka.

## Frontend kuralları (Faz 4'te geçerli)

- **TypeScript strict mode.** `any` kullanma, gerçekten gerekiyorsa `unknown` kullan.
- **Her `.ts` dosyası bir şey yapsın.** 500 satırı geçen dosya bölünmeli.
- **CSS için Tailwind kullan.** Özel CSS sadece gerçekten özel bir şey için.

## Git commit kuralları

- **Conventional commits.** `feat: add GTFS import command`, `fix: handle missing shape_id in stop_times`
- **Her commit çalışır durumda olmalı.** Broken commit atma.
- **Faz tamamlanınca tag at.** `git tag phase-1-complete`

---

# 🚫 YAPMA (kırmızı çizgiler)

- **Docker kullanma.** Geliştirici Docker istemiyor. Native kurulum.
- **Migration'ları elle düzenleme.** Sadece modeli değiştir, `makemigrations` çalıştır.
- **Production secret'larını git'e commit etme.** `.env` dosyası `.gitignore`'da olmalı.
- **Rate limit kararını değiştirme.** 60 saniyede bir İETT çağrısı. Daha sık yapma. Docümana bağlı kal.
- **Doküman dışına çıkma.** Eğer dokümanın dışında bir şey yapmak gerektiğini düşünüyorsan, önce dokümana ek yap, onay al, sonra yap.
- **Scope creep yapma.** Kullanıcı hesabı, rota planlama gibi ileri faz özelliklerini Faz 1'e sokma.

---

# 🚀 ŞİMDİ YAP

1. `MINI_ISTANBUL_3D_SPEC.md`'yi oku (tamamen).
2. Test scriptlerine göz at (test_*.py dosyaları) — İETT API'yle nasıl konuşuluyor görmek için referans.
3. Faz 1'in çıktı listesini (dokümanın Bölüm 7.1) aç, **implementation plan sun**. Plan şunları içersin:
   - Django proje kurulum adımları (komutlar dahil)
   - Model tasarımı özeti (hangi app'te hangi model)
   - `import_gtfs` komutunun çalışma mantığı
   - İlk commit'in içeriği
   - Tahmini süre
4. Geliştirici onayını bekle.
5. Başla.

**İlk mesajında yalnızca plan olsun, kod yazmaya başlama.**

---

# 💬 GELİŞTİRİCİ ILE İLETİŞİM

- Türkçe konuş (geliştirici Türkçe tercih ediyor)
- Teknik terimler İngilizce kalabilir (migration, endpoint, interpolation vs.)
- Sorularını spesifik sor — "Nasıl yapalım?" değil, "A mı B mi?"
- Progress'i özet olarak paylaş, her dosyayı tek tek gösterme
- Hata aldığında önce kendin debug et, çözemezsen net olarak anlat

Başarılar. Dokümanı oku, planı sun, başlayalım.
