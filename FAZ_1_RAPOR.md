# Faz 1 Rapor

**Tarih:** 22 Nisan 2026
**Durum:** Tamamlandı
**Git tag:** `phase-1-complete`

---

## Ne yapıldı

İBB'nin yayınladığı statik GTFS verilerini indiren, PostGIS'e aktaran
ve REST API üzerinden sorgulatan bir Django backend'i kuruldu. İki
ayrı feed var (İETT ve Public Transport), ikisi de tamamen farklı
kurallarla yazılmış CSV dosyaları — bu yüzden `gtfs-kit` gibi hazır
kütüphaneler işe yaramadı, ham `pandas.read_csv` + auto-detect
encoding/delimiter ile kendi import pipeline'ımız yazıldı.

Bu pipeline'ın içine geliştirme sürecinde çıkan 10 farklı veri kalitesi
bulgusuna karşı savunma katmanları eklendi (koordinat bozulması, encoding
karmaşası, route_id çakışması, renk metadata'sı eksikliği vs.). Her bir
bulgu spec Ek A'da kayıt altında. Sonuç olarak 22.458 durak, 9.773 hat,
953 shape, 150.012 trip ve 1.248.454 stop_time kaydı PostGIS'e temiz
şekilde yüklendi.

Üstüne DRF endpoint'leri (spec §6.3'teki tüm rotalar) ve bir Leaflet
preview sayfası geldi. Preview sayfası görsel sanat değil — veri
bütünlüğünü gözle doğrulamak için: "M4 Kadıköy'den Tavşantepe'ye gerçekten
doğru yönde gidiyor mu, Marmaray Boğaz'ı doğru yerden geçiyor mu" gibi.

---

## Sayısal özet

| Metrik | Değer |
|---|---|
| Agency | 9 |
| Route | 9.773 |
| Stop | 22.458 |
| Shape | 953 |
| Trip | 150.012 |
| StopTime | 1.248.454 |
| Git commit sayısı | 11 |
| Tam GTFS import süresi | ~4 dakika |
| Tam GTFS download süresi | ~5 dakika |

---

## Sürpriz kutusu — İBB verisi

Planlama aşamasında "GTFS açık standart, import hızlı olur" dedik.
Gerçekte 10 farklı yerde takıldık. En çarpıcı üç tanesi:

**Route_id çakışması (A.3).** Public feed (Mart 2024) ve İETT feed
(Mart 2026) aynı route_id değerlerini tamamen farklı hatlara atamış —
tam 118 tanesi. Örnek: Public'te `1296` = M1A Metro, İETT'de `1296` =
19E Otobüs. İlk upsert denemesinde İETT last-wins olduğu için M1A/M2/M3
gibi metro hatları otobüslerle overwrite olup shape'leri kayboluyordu.
Çözüm: route_id'ye feed prefix (`public:1296`, `iett:1296`). Üretim
koduna bir nebze bilgi kaçağı ama veri bütünlüğü korundu.

**Excel Turkish locale bozulması (A.2).** İETT'nin stops.csv'sindeki
15.378 satırda koordinatlar şöyle görünüyordu: `410.191.700.005.564`.
Biri bu dosyayı Excel'de açıp kaydetmiş, Türkçe locale nokta'yı binlik
ayracı sanmış, gerçek değer `41.0191700005564`. `_sanitize_coord()`
helper'ı ilk noktayı koruyup diğerlerini silerek %99.9 kurtardı. Excel
İstanbul toplu taşımasında yarı gizli bir veri tahrip aracı.

**`#NAN` renk bug'ı (A.10).** Bu Faz 1'in en sinsi bug'ıydı, aşağıda
ayrı başlık açtım.

Kalan 7 bulgu (encoding iki aşamalı doğrulaması, bbox kalibrasyonu,
shape_pt_sequence string sort, yanıltıcı stop_times.zip, İETT'de
shapes.csv yokluğu, direction_id NaN'ları, embedded comma malformed
route) spec Ek A'da detaylı. Bir noktadan sonra veri temizliği bir
projenin kendisi kadar zaman alıyor — ve bu aslında normal.

---

## En zorlu bug

`#NAN` renk bug'ı iki farklı açıdan öğretici oldu.

**Teknik boyut:** Public feed'de `route_color` kolonu var ama 499
satırda da boş. `pandas.read_csv(na_values=[""], dtype=str)` okuduğunda
boş hücreler `float('nan')` oluyor, sonra `str(nan)` = `"nan"` string'i
geliyor. `"nan"` truthy bir string, yani `value or default` zinciri
tetiklenmiyor. DB'ye `"#NAN"` yazılıyor. Leaflet bu renkle SVG
`stroke="#NAN"` üretiyor, browser geçersiz değer diye sessizce atıyor —
polyline haritaya eklenmiş sayılıyor (counter "30 hat çizildi" diyor),
ama görünmüyor.

**Asıl ders: bug'lar birbirini gizleyebilir.** Bu `#NAN` aslında baştan
beri oradaymış. Ama route_id çakışmasını çözmeden önce, İETT'nin
last-wins upsert'i tüm public `#NAN`'lerini `#000000`'a overwrite ediyordu.
Yani prefix fix'i bir bug'ı çözdü ama başka bir bug'ı **görünür yaptı**.
Faz 2'de benzer bir şey olabilir — adaptör katmanını çözdüğümüzde rate
limiter'ın altında uyuyan başka bir şey ortaya çıkabilir.

Çözüm iki katmanlı: backend'de `_clean_hex()` regex-validated hex
normalizer, frontend'de `HEX_RE` guard + turuncu fallback sayacı.
Defense-in-depth — DB'ye bozuk renk bir daha sızarsa (başka bir dataset'ten,
başka bir yoldan) frontend anında turuncu çizgi + kırmızı sayaç gösterir.
Sessiz başarısızlık yok.

Reimport sonrası 498 bozuk satır temizlendi, DB'de `#NAN` kalmadı.

---

## Mimari kararlar

**`gtfs-kit`'ten vazgeçmek.** İlk plan standart kütüphane kullanmaktı.
Ama kütüphane UTF-8 + virgül bekliyor, iki feed de farklı kurallarla
geliyor (İETT: UTF-8-BOM + noktalı virgül, Public: cp1254 + virgül).
Kütüphaneyi zorlamak yerine ham pandas + kendi encoding/delimiter
detection'ımızı yazdık. Bu bize ileride SOAP verisi geldiğinde de
benzer esneklik verecek.

**Route_id prefix (`public:`/`iett:`).** Feed kimliğini primary key'e
kaçırmak kurumsal olarak tatsız ama pratik olarak tek temiz çözüm.
Alternatif (composite key, ayrı feed_id kolonu) hem daha karmaşık
hem daha kırılgan olurdu.

**`_clean_hex` + frontend regex guard ikilisi.** Backend fix tek başına
yeterdi ama ileride başka bir veri kaynağından (SOAP? Faz 2+?) aynı
sızıntı olursa yeniden debug etmek istemeyiz. Frontend turuncu fallback
sayacı erken uyarı sistemi.

**İki aşamalı encoding detection.** BOM varlığı UTF-8 olduğunu garanti
etmiyor — Excel cp1254 içeriği BOM'la birlikte save edebiliyor. Önce
BOM'a bak, sonra içeriği decode ederek doğrula. Küçük ama önemli bir
detay.

---

## Faz 2'ye ne hazır, ne eksik

**Hazır altyapı:**
- PostGIS veritabanı ve GTFS şeması (Agency/Route/Stop/Shape/Trip/StopTime)
- REST API endpoint'leri — Faz 2'de yeni `realtime` app'i bu schema'nın
  üstüne oturacak
- Import pipeline — feed güncellenirse tek komutla yeniden yüklenir
- Preview sayfası — Faz 2'de canlı veri geldiğinde hızlı smoke test
  için burada test edebiliriz
- pg_dump backup mekanizması — regression riski varsa geri dönüş yolu
  açık
- 11 commit'lik temiz git history + tag — hangi değişiklik ne zaman
  oldu net

**Eksik altyapı:**
- Memurai (Redis for Windows) — Faz 2'nin ilk işi
- Celery worker + beat
- İETT SOAP adaptörü (ham `requests` ile, `zeep` değil çünkü WSDL broken)
- Redis sliding window rate limiter
- Distributed lock (multi-worker güvenliği için)
- Admin paneli izleme sayfası (rate limit kullanım oranı grafiği)
- Stale cache fallback (API çöktüğünde UI'ın "veri gecikiyor" demesi)

---

## Bilinmeyenler

Faz 2'ye başlamadan önce üç şey doğrulanmalı — hepsi Faz 1 süresince
test edilmedi çünkü gereksiz rate limit tüketimi olurdu:

1. **`GetIettArsivGorev_json(Tarih)` bugünkü tarih için çalışıyor mu?**
   Bu metot kapı no → hat eşlemesini veriyor, Faz 2'nin temel taşı.
   Spec'te geçmiş için çalıştığı yazıyor, bugün için belirsiz.
   Çalışmazsa araçlar "bilinmeyen hat" olarak görünür, UX kırılmaz
   ama UI mesajı net olmalı.

2. **Metro İstanbul REST API rate limit paylaşımı.** İETT SOAP ile
   aynı İBB gateway'inden geçiyor mu, ayrı mı? Bilmiyoruz. Eğer aynı
   gateway'se, iki API'yi aynı sliding window'da sayıp kotayı paylaşmak
   gerekir. Ayrı gateway'se her birinin kendi sayacı olur.

3. **Memurai performansı.** Linux Redis ile birebir uyumlu diyorlar
   ama Celery + Channels + pub/sub yükü altında nasıl davranıyor test
   edilmedi. Faz 2'nin ilk günü basit bir smoke test yeter.

---

## Yağız için net öneri

Faz 2'ye tam hızla girmeden önce yarım günlük bir "pre-flight" yapalım.
Üç küçük test:

1. **Memurai kurulumu ve smoke test.** Kur, Redis CLI bağlantısı al,
   basit `SET/GET` yap. 15 dakika.

2. **`GetIettArsivGorev_json` bugün için doğrulama.** Mevcut
   `_research/test_*.py` script'lerinden birini uyarla, tek çağrı at,
   response içinde bugünkü sefer görevlerini gör. 30 dakika.
   **Bir çağrı** — rate limit kotasını yememek için.

3. **Metro İstanbul REST API'sine ilk bakış.** `GetLines`, `GetTimeTable`
   endpoint'lerini dene, auth gerekip gerekmediğini tespit et, 2-3
   istek aralıkla rate limit davranışını gözle (İETT'dekiyle paralel
   mi?). 1 saat.

Bu üç test Faz 2'nin ilk haftasını güvene alır. Her biri tek başına
Faz 2 yapısına yerleştirilemeyecek kadar küçük, ama öncesinde yapılmadan
Faz 2 implementasyonu varsayımlar üzerine kurulur — ve en sonunda
varsayım yanlış çıkarsa refactor büyük olur.

Onaylarsan bu üç testi ayrı bir "Faz 1.5 — Pre-flight" gününe atarım,
sonuçları rapor dosyasına ekler, ondan sonra Faz 2'nin ilk commit'ine
başlarız.
