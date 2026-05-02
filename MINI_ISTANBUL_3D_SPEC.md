# Mini Istanbul 3D — Teknik Spesifikasyon ve Geliştirme Planı

> İstanbul'un toplu taşıma ağının gerçek zamanlı 3D dijital haritası.
> [Mini Tokyo 3D](https://github.com/nagix/mini-tokyo-3d)'den ilham alınmıştır.

**Versiyon:** 0.7.4 (Yol B + stale vehicle.timestamp filter, 2026-05-02)
**Hedef:** Antigravity agent ile geliştirilecek, Python Django tabanlı bir web uygulaması
**Lisans:** MIT (planlanıyor)
**Statü:** Faz 1-5 tamamlandı (2026-05-01). Faz 2 polish 5j-ii eklendi (2026-05-02). Faz 5.5 (OSM yol snapping) ve Faz 6 (cilalama) paralel açık.

> **v0.7.4 değişiklikleri (2026-05-02):** Yol B (vehicle.route_id semantiği SHATKODU short_name'den canonical Route.route_id PK'sına geçti, β filtre `agency=IETT, route_type=3` + alfabetik tie-breaker) ve stale vehicle.timestamp filter (5j-ii, 180s threshold + heartbeat counter) eklendi. Yeni Ek A.15 (fleet endpoint stale konum davranışı) ve Ek A.16 (İETT GTFS stop_times coverage 139/9274). Realtime suite 165/165, frontend 210/210 yeşil.

> **v0.8 değişiklikleri (2026-04-26):** Faz 2 (canlı veri adaptörü) `d52024a` commit'iyle tamamlandı (realtime suite 121/121 yeşil). Faz 2 Adım 5i smoke test'i sırasında UX yön değişikliği yapıldı: tüm 6911 araç haritada ham nokta olarak gösterilecek, hat filtresi frontend'de görsel katman olarak işlenecek. Bu pivot WebSocket modelini de sadeleştirdi: tek `vehicles:all` Channels group'u, hat-bazlı kanallar Faz 5'e (metro/marmaray/vapur simülasyonu) ertelendi. Değişen bölümler:
> - §5.7 sonu — yeni alt-bölüm "v0.8 pivot" (rationale, hat-bazlı yapının Faz 5'te geri dönüşü, bandwidth karşılaştırması)
> - §6.4 başı — Faz 3 sadeleştirilmiş protokol prelude (orijinal hat-merkezli `subscribe`/`subscription_ack` modeli Faz 5 için altta korundu)
>
> Pipeline çekirdeği (adapter, rate limiter, lock, mapping cache, enrichment, fetch task) değişmedi — Adım 6b'de fetch task'ın son adımı tek `SET vehicles:all` + `group_send` modeline indirgenir.

> **v0.7 değişiklikleri (2026-04-24):** UI modeli **araç-merkezli**den **hat-merkezli**ye taşındı. Kullanıcı artık bireysel araç değil, hat izler ("29B hattı ne yapıyor"). Bazı kategoriler sürekli görünür (metro, tramvay, füniküler, Marmaray, metrobüs, vapur), otobüs hatları opt-in (kullanıcı seçerse görünür). Değişen bölümler:
> - Yeni §3.3 "Mod Sınıflandırması ve Görünürlük Politikası"
> - Yeni §5.7 "Hat-Merkezli Pipeline" (cache stratejisi, pub/sub modeli)
> - §5.3 WebSocket mesaj formatı — per-route update (her hat ayrı mesaj)
> - §6.3 REST API — yeni endpoint'ler: `/api/routes/active/`, `/api/routes/{id}/live/`
> - §6.4 WebSocket protokolü — subscribe modeli `route_ids` odaklı
> - §7 Faz 2-4 — hat-merkezli pipeline ve UI paneli entegrasyonu
> - Yeni US-9 (hat izleme)
>
> Pipeline çekirdeği (adapter, rate limiter, lock, parser'lar) değişmedi — hat-merkezli mantık fetch task'ının son adımında `groupby(route_id)` olarak ekleniyor.

> **v0.6.1 değişiklikleri (2026-04-23):** Ek A.11 düzeltildi (endpoint yanlış varsayımıydı), A.13 ve A.14 eklendi (intra-day refresh pattern, zaman-bağımlı mapping).

> **v0.3 değişiklikleri (2026-04-19):** İETT SOAP servisine 3 farklı ampirik test yapıldı (token uyumluluğu, dayanıklılık, backend refresh rate). Ölçülen kritik gerçekler:
> - **Rate limit:** ~40 dakikalık sliding window, ~72 istek/pencere. İhlalde ~30 dakika cooldown.
> - **Backend refresh rate:** ~60 saniye (ort. 60.3s, min 57.1s, max 68.1s).
> - **Authentication:** Servis anonim erişime açık, CKAN token'ı SOAP'ta etkisiz (ama zararsız).
>
> v0.2'deki "3 seçenek" belirsizliği kaldırıldı, tek strateji kesinleşti: **60 saniye aralıklı sunucu çağrısı + client-side interpolation**. Detaylar Bölüm 4.2.1 ve 5.4'te.

> **v0.2 değişiklikleri:** İETT resmi web servis dokümanı (v1.5) incelendi. Rate limit ve endpoint yapısı keşfedildi.

---

## 1. Proje Özeti

### Ne yapıyoruz?
İstanbul'daki otobüs, metro, Marmaray ve vapurların gerçek zamanlı konumlarını 3D bir harita üzerinde canlı olarak gösteren web uygulaması. Kullanıcı bir metro istasyonuna tıklayınca yaklaşan trenleri, bir hattı seçince o hattaki tüm araçları, bir durakta bekleyince varış sürelerini görebilir. Harita pitch/bearing ile döndürülebilir, binalar 3D'de yükseltilmiştir, Boğaz ve tepeler topografik olarak doğrudur.

**Görünüm modeli hat-merkezli:** Kullanıcı bireysel araç değil, hat takip eder ("29B ne yapıyor", "M2 hattındaki trenler nerede"). Sürekli görünür kategoriler — metro (M1-M11), tramvay (T1-T5), füniküler (F1-F4), Marmaray, metrobüs (10 hat), vapur — açılışta haritada yer alır. İETT'nin ~800 normal otobüs hattı varsayılan olarak gizlidir; kullanıcı hat adı arayarak veya panelden seçerek haritaya ekler (bir nevi "favori hatlara abone olma"). Detaylar §3.3'te.

### Niye yapıyoruz?
Tokyo, Londra, Berlin, Singapur gibi şehirlerin böyle görselleştirmeleri var. İstanbul gibi 16 milyon nüfuslu, karmaşık bir toplu taşıma ağı olan bir metropol için yok. İBB açık veri portalı bu tür bir uygulamayı mümkün kılacak verileri yayınlıyor — sadece kimse oturup yapmamış. Proje:

- Açık kaynak olarak yayınlanır, topluluk tarafından geliştirilebilir
- Portföy / showcase niteliğinde bir GIS + full-stack yetkinlik göstergesidir
- İBB'nin açık veri ekosistemine somut bir kullanım örneği sunar

### Kimler kullanacak?
Öncelikli kullanıcılar İstanbullu toplu taşıma kullanıcıları ve turistlerdir. İkincil kullanıcılar ulaşım araştırmacıları, şehir plancıları ve geliştiricilerdir (API erişimiyle).

### Nasıl farklılaşıyor?
Mevcut İETT "Otobüsüm Nerede" uygulaması veriyi 2D sunuyor, turist dostu değil, İngilizce yok, sadece otobüs. Google Maps canlı araç konumu göstermiyor. Moovit var ama 3D değil ve reklam ağırlıklı. Mini Istanbul 3D:

- **3D ve görsel olarak etkileyici**
- **Tüm toplu taşıma modları tek bir yerde**
- **Türkçe + İngilizce**
- **Ücretsiz ve reklamsız**

---

## 2. Kullanıcı Hikâyeleri (User Stories)

### Acil kullanım
**US-1:** Bir durağa gelen kullanıcı, o duraktan geçen bir sonraki araçların kaç dakika sonra geleceğini görmek ister.

**US-2:** Metro istasyonunda bekleyen kullanıcı, trenin şu an nerede olduğunu ve kaç dakika sonra geleceğini görmek ister.

**US-3:** Yolda yürüyen kullanıcı, harita üzerinde en yakın durağı ve oradan geçen hatları görmek ister.

### Keşif
**US-4:** Turist, İstanbul'daki toplu taşıma ağının genel yapısını tek bir ekrana bakarak anlamak ister (hangi metro nereye gidiyor, vapur hatları nereler vs.).

**US-5:** Kullanıcı haritanın varsayılan görünümünde metro, tramvay, füniküler, Marmaray, metrobüs ve vapurların canlı durumunu görür. İlgilendiği bir otobüs hattını (örn. 29B) listeden seçerek o hatta ait araçları da haritaya ekler; seçimden çıkarınca haritadan temizler.

**US-6:** Kullanıcı iki nokta seçip aralarında en uygun toplu taşıma rotasını görmek ister (Faz 6+, opsiyonel).

### Teknik / Meraklı
**US-7:** Geliştirici, uygulamanın sunduğu REST API'yi kullanarak kendi uygulamasına İstanbul toplu taşıma verisi entegre etmek ister.

**US-8:** Araştırmacı, geçmiş bir tarih aralığındaki sefer verilerini indirmek ister (Faz 7+).

**US-9:** Kullanıcı 29B hattını seçer; o hatta ait tüm araçların güzergâh boyunca dağılımını, hangi durakta hangi aracın olduğunu, araçlar arasındaki aralıkları (headway) görür. Hat tıklanınca polyline vurgulanır, diğer hatların araçları arka plana çekilir.

---

## 3. Kapsam (Scope)

### İlk sürüm (v1.0) — MVP
**Dahil:**
- **Coğrafi kapsam:** İstanbul geneli (39 ilçe)
- **Ulaşım modları:** Metro (M1-M11), tramvay (T1-T5), füniküler (F1-F4), Marmaray, metrobüs (10 hat), vapur (İDO + Şehir Hatları) **sürekli görünür**; İETT normal otobüs hatları (~800) kullanıcı seçimine göre (opt-in). Sınıflandırma detayı §3.3'te.
- **Canlı veri:** Otobüsler (metrobüs dahil) gerçek konum; metro, tramvay, füniküler, Marmaray, vapur tarife-bazlı simülasyon
- **Harita:** OpenStreetMap tabanlı, 3D bina extrusion, 3D terrain
- **Etkileşim:** Durak tıklama, hat tıklama, araç tıklama, hat arama/seçim paneli, zoom/pan/rotate/pitch
- **Diller:** Türkçe (varsayılan) ve İngilizce
- **Cihaz:** Masaüstü (öncelik) ve mobil tarayıcı (responsive)

**Hariç (ilk sürümde yapılmayacak):**
- Rota planlama (origin→destination)
- Geçmiş veri / zaman kaydırma
- Kullanıcı hesapları, favoriler
- Push bildirimleri, mobil native app
- Minibüs, dolmuş, taksi, özel halk otobüsü hatları
- Trafik verisi, hava durumu entegrasyonu

### Sonraki sürümler (roadmap)
- **v1.1:** Kullanıcı hesabı, favori duraklar/hatlar
- **v1.2:** Rota planlama (OpenTripPlanner entegrasyonu)
- **v1.3:** Minibüs ve dolmuş hatları
- **v1.4:** Landmark 3D modelleri (Ayasofya, Galata Kulesi vb.)
- **v2.0:** Zaman kaydırma, geçmiş veri analizi
- **v2.1:** Mobil native uygulama (opsiyonel)

### 3.3. Mod Sınıflandırması ve Görünürlük Politikası

İstanbul'un toplu taşıma ağı ölçek olarak büyük: Faz 1 sonunda DB'de 9.773 Route kaydı var (hat × yön × varyant × feed çarpımı dahil), her biri farklı yoğunlukta. Hepsini aynı anda haritada göstermek hem görsel kirlilik yaratır hem performans problemi çıkarır. Bu yüzden hatları **görünürlük politikası**na göre iki kategoriye ayırıyoruz.

**DB row vs unique fiziksel hat.** Route tablosu `route_id` bazında unique; aynı fiziksel hattın gidiş/dönüş yönleri, varyantları ve iki feed (`public:` + `iett:`) prefix'i ayrı row'lar üretiyor. Mesela `AVR1` short_name'i 149 row'a sahip, `M7` 29 row'a. Hat-merkezli UI için önemli olan **unique `short_name`** sayısı, row sayısı değil. Aşağıdaki tablo ikisini de gösteriyor; subscribe ve kanal kararları unique'e dayalı.

#### Sürekli görünür (varsayılan açık)

Kullanıcı müdahalesi olmadan haritada görünen, kapasitesi yönetilebilir ve "şehir omurgası" niteliğinde hatlar. Açılışta polyline'ları çizilir, üstlerinde araçlar hareket eder.

**Tablo Faz 2 Adım 5a discovery query sonuçlarıyla doldurulmuştur (2026-04-24, DB snapshot: 9.773 Route):**

| Kategori | Tespit mekanizması | Unique short_name | DB row | Gerçek liste | Canlı veri | Hareket kaynağı |
|---|---|---|---|---|---|---|
| **Metro** | `short_name` regex `^M\d+[A-Z]?$` | **12** | 60 | M1A, M1B, M2, M2A, M3, M3A, M4, M5, M6, M7, M8, M9 | Yok | Tarife simülasyonu (Faz 5) |
| **Tramvay** | `short_name` regex `^T\d+$` | **4** | 5 | T1, T2, T3, T4 | Yok | Tarife simülasyonu (Faz 5) |
| **Füniküler** | `short_name` regex `^F\d+$` | **3** | 12 | F1, F2, F3 | Yok | Tarife simülasyonu (Faz 5) |
| **Marmaray** | `agency_id=2 AND route_type=2` | **3** | 3 | Marmaray, Marmaray1, Marmaray2 | Yok | Tarife simülasyonu (Faz 5) |
| **Metrobüs** | `short_name` whitelist (aşağıda) | **10** | 113 | 34, 34A, 34AS, 34B, 34BZ, 34C, 34G, 34T, 34U, 34Z | **Var (İETT SOAP)** | Canlı GPS |
| **Vapur** | `agency_id=1 AND route_type=4` | **~99** | 100 | (kısaltma isimler, "BOSTANCI-B.KÖY" vs.) | Yok | Tarife simülasyonu (Faz 5) |

**Toplam sürekli görünür:** 131 unique short_name. Fiziksel dünya karşılığı ~131 polyline, ~500-800 hareketli araç/obje anlık ekranda (metrobüs canlı filosu + raylı/vapur aktif trip simülasyonları).

**Feed eksikleri (gözlemden):** T5 tramvay ve F4 füniküler İstanbul'da gerçekten servis veriyor ancak İBB GTFS feed'inde şu anda yoklar. Faz 1 import'unda DB'ye girmediler. Spec bu iki hattı "dahil ama henüz feed'de yok" olarak belgeliyor — İBB feed'i güncellenirse otomatik dahil olacaklar, kod tarafında özel bir iş gerekmez.

**Metrobüs whitelist** (değişmez, İETT'nin resmi hat listesi, tümü DB'de mevcut):

```python
METROBUS_ROUTES = {
    "34",    # Avcılar - Zincirlikuyu (ana)
    "34A",   # Cevizlibağ - Söğütlüçeşme
    "34AS",  # Avcılar - Söğütlüçeşme
    "34B",   # Beylikdüzü - Avcılar
    "34BZ",  # Beylikdüzü - Zincirlikuyu
    "34C",   # Beylikdüzü - Cevizlibağ
    "34G",   # Beylikdüzü - Söğütlüçeşme (gece)
    "34T",   # Avcılar - Topkapı
    "34U",   # Uzunçayır - Zincirlikuyu
    "34Z",   # Zincirlikuyu - Söğütlüçeşme
}
```

Whitelist neden regex değil: `^34[A-Z]*$` pattern'i `340`, `341` gibi normal İETT otobüs hatlarını ve gelecekte eklenebilecek `34D`, `34X` gibi değişiklikleri yanlış pozitif/negatif yakalar. Sabit liste, yılda 1-2 kez elle güncellenen bir veri. Discovery query (Adım 5a) whitelist'teki 10 hat için tam match doğruladı, 34-prefix'li başka short_name DB'de yok.

#### Opt-in (varsayılan kapalı)

**1.080 unique short_name** (~8.885 DB row), sürekli-görünür kategorilerinin dışında kalan `agency_id=9` (İETT) `route_type=3` hatları. Normal İETT otobüs hatları bu grupta. Kullanıcı akışı:

1. Açılışta haritada görünmezler
2. Sağda "Hatlar" paneli: arama kutusu + hat listesi (short_name + long_name)
3. Kullanıcı hat seçer → haritaya polyline + araçları eklenir, WebSocket subscribe gönderilir
4. Seçimden çıkarır → haritadan temizlenir

**Neden opt-in?** 1.080 hat × ortalama ~6 araç/hat = ~6.900 otobüs anlık render; hem GPU baskısı hem "her şey renkli çizgi" kirliliği. Kullanıcı gerçekten ilgilendiği 1-5 hattı izliyor, geri kalan arka plan gürültü.

#### Kapsam dışı (MVP'ye dahil değil)

| Kategori | Tespit | DB row | Kapsam |
|---|---|---|---|
| **Minibüs** | `route_type=9` (GTFS extended) | 317 | v1.3'e ertelendi (spec §3.2) |
| **Taksi-dolmuş** | `route_type=10` (GTFS extended) | 58 | v1.3'e ertelendi |

Discovery query (2026-04-24) iki route type'ı da `agency_id=4` (Minibus) ve `agency_id=5` (Taksi Dolmus) ile tam eşledi. Bu kayıtlar pipeline'a dahil edilmeyecek, mapping'e girmeyecek, `active_routes` listesine eklenmeyecek. Frontend filtreleme panelinde de görünmezler.

#### Kanal ve subscribe granülerliği — `short_name` bazlı

Redis pub/sub kanalları ve WebSocket subscribe'ı **`short_name` bazlı** yapılır, `route_id` bazlı değil:

- Redis channel: `vehicles:route:{short_name}` (ör. `vehicles:route:29B`, `vehicles:route:M2`)
- Redis cache key: `vehicles:route:{short_name}` aynı namespace, 120sn TTL
- WebSocket subscribe: `{"route_ids": ["29B", "M2", "34BZ"]}` — semantik olarak short_name listesi (adlandırma spec'te bu biçimde sabit kalır, ama değerler short_name)

**Neden short_name:**
- Kullanıcı mental modeli: "29B" izler, `iett:1296` veya `public:25378` değil
- 1 fiziksel hat × 29 DB row varsa 29 kanal saçma — 1 kanal mantıklı
- Frontend arama input'u short_name'i döndürür doğal olarak

**Enrichment ile mapping bağı:** Mapping cache (§5.7) `SHATKODU` değerlerini `short_name` namespace'i olarak kullanır. Faz 2 Adım 5b/5c'de mapping'den gelen `hat_kodu` değerlerinin DB'deki `short_name` kolonuyla ne kadar hizalı olduğu doğrulanacak. %100 hizalı değilse (mapping'de olup DB'de olmayan veya tersi), "unknown route" sayacı admin panelde görünür, araç `route_id=None` olarak pipeline'dan geçer.

#### Kategori doğrulaması

Bu tablonun rakamları **Faz 2 Adım 5a** (2026-04-24) discovery query'sinden gelir. Spec'e zamanla yeni kategoriler eklenirse ya da İBB feed'inde değişiklik olursa discovery query yeniden koşturulup tablo güncellenir.


---

## 4. Veri Kaynakları

### 4.1. Statik GTFS Verileri (Kurulum Sırasında Bir Kez İndirilir)

**Kaynak:** İBB Açık Veri Portalı — https://data.ibb.gov.tr

**İki ayrı veri seti indirilecek:**

1. **İETT GTFS** — https://data.ibb.gov.tr/dataset/iett-gtfs-verisi
   - İETT otobüs hatları, durakları, sefer tarifeleri
   - Standart GTFS formatında (agency.txt, stops.txt, routes.txt, trips.txt, stop_times.txt, shapes.txt, calendar.txt)

2. **Genel Toplu Ulaşım GTFS** — https://data.ibb.gov.tr/dataset/public-transport-gtfs-data
   - Metro, Marmaray, İDO, Turyol, Dentur Avrasya, minibüs, taksi dolmuş hatları

**Not:** GTFS dosyaları kurulum sırasında indirilir ve Django yönetim komutu ile PostGIS veritabanına aktarılır. Geliştirici lokalde `python manage.py import_gtfs` komutunu çalıştırır.

### 4.2. Canlı Veri API'leri

**4.2.1. İETT Canlı Otobüs Konumları (SOAP servisleri)**

İETT, çeşitli SOAP web servisleri üzerinden veri yayınlıyor. **Resmi dokümantasyon:** [İETT Web Servis Kullanım Dokümanı v1.5](https://data.ibb.gov.tr/dataset/3e32bb5d-2936-41eb-bdc7-65b843487e99/resource/6821f452-f6ff-49e9-940a-d4ebfc78f03e/download/iett-web-servis-kullanm-dokumanv.1.2.pdf) (İBB tarafından yayınlanmış PDF).

**Canlı filo konumları için iki endpoint:**

| Metod | Parametre | Ne döndürür? |
|---|---|---|
| `GetFiloAracKonum_json()` | yok | **Tüm aktif filonun** konumları (~6900 araç tek çağrıda, ~1.1 MB payload) — Akyolbil servisi |
| `GetHatOtoKonum_json(HatNo)` | hat kodu (zorunlu) | Belirli bir hattaki araçların konumları |

**Endpoint:** `https://api.ibb.gov.tr/iett/FiloDurum/SeferGerceklesme.asmx`

**Authentication:** Servis **anonim erişime açık**. data.ibb.gov.tr'de hesap açıp API token almak SOAP servisi için bir etki yaratmıyor (test edildi). Token ile veya tokensız aynı sonuç döner.

#### Ampirik Test Sonuçları (2026-04-19)

Geliştirmeye başlamadan önce servisi üç ayrı testle ölçtük. Sonuçlar stratejimizi belirliyor:

**Test 1 — Token uyumluluğu:**
- CKAN API token'ı header'da, query string'de, hiç yok — üçü de aynı sonucu verdi
- **Çıkarım:** SOAP servisi authentication gerektirmiyor

**Test 2 — Dayanıklılık (200 çağrı, 3 saniye aralık):**
- İlk 72 istek başarılı (~5 dakika içinde, 16:14:49 → 16:20:01)
- 73. istekten itibaren HTTP 500 + "Policy Falsified" (rate limit tetiklendi)
- Yeniden açılma: 17:00:33 (ilk block'tan ~40 dakika sonra)
- **Çıkarım:** Rate limit **saat bazlı değil, ~40 dakikalık sliding window**. Pencere başına ~72 istek hakkı var. İhlalde ~30 dakika cooldown.

**Test 3 — Backend refresh rate (10 saniye aralıklı 30 snapshot):**
- Yeni veri gelme aralıkları: 57.1s, 57.7s, 58.3s, 68.1s
- Ortalama: **60.3 saniye** (min 57.1, max 68.1)
- **Çıkarım:** Backend her ~60 saniyede bir veri yayınlıyor. Daha sık çağrı yapmak aynı veriyi döndürür (bandwidth ve rate limit israfı).

#### Kesinleşmiş Strateji: 60 saniyede bir çağrı + client-side interpolation

**Sunucu tarafı:**
- Celery beat görevi **her 60 saniyede** `GetFiloAracKonum_json()` çağırır
- Sonuç Redis'e yazılır (TTL 5 dakika), WebSocket üzerinden frontend'e yayınlanır
- **Rate limit marjı:** Saatte 60 çağrı yapılır, 40-dk pencerede 40 çağrı. Güvenli marj: pencere kapasitesinin %44'ü kullanılır, %56 boşta kalır (API arıza/retry senaryoları için tampon).
- Savunma katmanları:
  1. Redis sayacı: son 40 dakikadaki çağrıları say, 60'a yaklaşırsa DURAKLA
  2. Distributed lock (Redis SETNX): birden fazla worker instance aynı anda çağrı yapmasın
  3. 429 veya 500 hata alınırsa exponential backoff (1dk, 2dk, 4dk, 8dk — en az 30dk)
  4. Stale cache fallback: son başarılı veri 5 dakika cache'te tutulur, API fail olursa gösterilir

**İstemci tarafı:**
- WebSocket üzerinden 60 saniyede bir yeni konum snapshot'ı alınır
- Her araç için **konum interpolasyonu** yapılır:
  - T₀ (önceki snapshot) ve T₁ (yeni snapshot) konumları arasında
  - Aracın ait olduğu hat `shapes.txt` geometrisine projekte edilir (polyline üzerinde closest point)
  - `requestAnimationFrame` ile 60 FPS akıcı animasyon
- Kullanıcı "canlı harita" algılar, gerçekte 60 saniye aralıklarla veri geliyor
- **Bu Mini Tokyo 3D'nin yaklaşımıdır.** Tokyo'da veri 15-30s aralıklarla gelir, aynı interpolation stratejisi uygulanır.

**Neden bu kombinasyon?**
- Daha sık çağrı yapmak → aynı veri döner, boşa trafik
- Daha az sık çağrı → araç pozisyonları eskir, interpolation hataları büyür
- Interpolation yok → araçlar 60 saniyede bir "zıplar", görsel bozulur
- Bu strateji **hem performans hem kullanıcı deneyimi açısından optimum**

#### Gelecek İyileştirme Notları

- **İBB'ye API key başvurusu:** data.ibb.gov.tr'de hesap açıldı (test amaçlı). SOAP servisinde etkisiz olduğu doğrulandı. Gelecekte İBB rate limit'ini artıran bir authenticated tier sunarsa düşünülebilir, ama mevcut durumda gerek yok.
- **Topluluk wrapper (hakanatak/dataibbgovtr, mekansal.herokuapp.com):** Mevcut SOAP servisinin üzerine yazılmış, rate limit sorununu çözmüyor. Referans olarak incelendi.

**Dönen veri formatı (`GetFiloAracKonum_json`):**

```json
{
  "Operator": "IETT",
  "Garaj": "HASANPASAGARAJI",
  "KapiNo": "C-231",
  "Saat": "14:23:45",
  "Boylam": "29.1032215",
  "Enlem": "41.0488515",
  "Hiz": "24",
  "Plaka": "34 HO 1234"
}
```

**ÖNEMLİ:** Bu veride **hat kodu YOK** — sadece `KapiNo`. Hat bilgisi başka servisten alınır:
- `GetIettArsivGorev_json(Tarih)` → gün başında bir kez çağrılır, `KapiNo → HatKodu` eşleme tablosu Redis'te cache'lenir
- Bazı araçların `Operator: OHO` gibi 3. parti operatör değerleri olabilir — bu araçlar İETT hattına atanmamış olabilir, UI'da "genel filo" olarak gösterilir

**Diğer faydalı İETT servisleri:**

| Servis | Endpoint | Ne işe yarar? |
|---|---|---|
| Hat-Durak-Güzergah | `UlasimAnaVeri/HatDurakGuzergah.asmx` | Durak, hat, garaj meta verisi (GTFS'e tamamlayıcı) |
| Duyurular | `UlasimDinamikVeri/Duyurular.asmx` | Hat kesintileri, anlık duyurular |
| Planlanan Sefer Saati | `UlasimAnaVeri/PlanlananSeferSaati.asmx` | Hat kalkış saatleri (iş günü / cumartesi / pazar) |
| İBB 360 Arşiv | `ibb/ibb360.asmx` | Geçmiş görev ve yolculuk verisi (Faz 7+) |
| Araç Özellikleri | `AracAnaVeri/AracOzellik.asmx` | Yakıt tüketimi (data analiz için) |

**Not:** Bu diğer servisler ayrı SOAP endpoint'leri, `SeferGerceklesme.asmx` ile rate limit paylaşımı **test edilmedi**. Muhtemelen ayrı ama doğrulanmalı. Güvenli yaklaşım: her servise kendi rate limit mantığı.

**Referans implementasyonlar:**
- [hakanatak/dataibbgovtr_python](https://github.com/hakanatak/dataibbgovtr_python) — Python, SOAP→GeoJSON wrapper
- [burakbayramli blog yazısı](https://burakbayramli.github.io/dersblog/sk/2023/01/iett-ibb-otobus-verisi.html) — `zeep` kullanım örnekleri
- [AydinAdn/IBB.Api](https://github.com/AydinAdn/IBB.Api) — .NET client kütüphanesi (endpoint referansı için)

**WSDL parse sorunu:** Python `zeep` kütüphanesi İETT'nin WSDL'ini strict modda parse ederken `GetBozukSatih_XMLAuthHeader` tanımı nedeniyle hata veriyor. Çözümler:
1. `zeep.Client(wsdl=..., strict=False)` ile başlat
2. Veya `zeep`'i tamamen atlayıp doğrudan `requests` ile ham SOAP envelope gönder (test script'lerinde kullanıldığı yöntem)

Geliştirmede 2. yöntem önerilir (bağımlılık az, hata daha az).

**4.2.2. Metro İstanbul REST API**

Metro İstanbul, REST endpoint'leri üzerinden aşağıdaki verileri veriyor:
- Base URL: `https://api.ibb.gov.tr/MetroIstanbul/api/MetroMobile/V2/`
- Endpoint'ler (data.ibb.gov.tr'de dokümante edilmiş):
  - `GetLines` — Tüm hatlar
  - `GetStationsByLineId` — Hat başına istasyonlar
  - `GetDirections` — Yön bilgisi
  - `GetTimeTable` — Sefer tarifeleri
  - `GetAnnouncements` — Anlık duyurular

**ÖNEMLİ KISITLAMA:** Metro İstanbul'un REST API'si canlı tren konumu vermiyor, sadece sefer tarifeleri. Bu yüzden trenleri **tarife-bazlı simülasyon** ile hareket ettiriyoruz (aşağıda 5.4'te açıklanıyor). Bu Mini Tokyo 3D'nin de yaptığı şey — birçok operatör canlı tren konumu yayınlamıyor.

**4.2.3. Marmaray ve Vapur Verileri**

- **Marmaray:** Sefer tarifeleri GTFS paketinde mevcut. Canlı konum verisi **yok**. Metro ile aynı tarife-bazlı simülasyon kullanılacak.
- **Şehir Hatları Vapurları:** GTFS paketinde mevcut. Canlı konum verisi **yok**. Tarife-bazlı simülasyon.

**4.2.4. Ek veri kaynağı: ulasav.csb.gov.tr**

Çevre, Şehircilik ve İklim Değişikliği Bakanlığı'nın "Türkiye Ulaşım Portalı" ([ulasav.csb.gov.tr](https://ulasav.csb.gov.tr/)) İETT Sefer Gerçekleşme servisini bir dataset olarak listeliyor. Bu ikincil kaynak — öncelik İBB'nin resmi API'si, ama İBB'de sorun yaşanırsa fallback olarak değerlendirilebilir. Rate limit dokümante değil, test edilmedi.

### 4.3. Veri Güncelleme Sıklığı

| Veri Türü | Güncelleme Sıklığı | Notlar |
|---|---|---|
| İETT canlı konumlar (sunucu) | **60 saniye** | Backend refresh rate'iyle (~60s) senkron. ~6900 araç fetch edilir, `KapiNo → HatKodu` enrichment sonrası hat bazlı gruplanır, ~800 hat key'ine yazılır |
| İETT canlı konumlar (istemci) | **Sürekli (60 FPS)** | Client-side interpolation ile akıcı render |
| Metro tarife simülasyonu | **Sürekli (client-side)** | `stop_times` + `shapes` ile interpolasyon |
| Marmaray simülasyonu | **Sürekli (client-side)** | Tarayıcı içinde interpolasyon |
| Vapur simülasyonu | **Sürekli (client-side)** | Tarayıcı içinde interpolasyon |
| Kapı no → hat eşlemesi | **Günde 1** | `GetIettArsivGorev_json` (ibb360.asmx) dün tarihiyle çağrılır, Redis'e yazılır |
| Statik GTFS | **Haftada 1** | Celery beat günlük kontrol, değişiklik varsa yeniden import |
| İETT duyuruları | **5 dakika** | `GetDuyurular_json` (ayrı endpoint) |
| Metro İstanbul duyuruları | **5 dakika** | `GetAnnouncements` |

**Rate limiting implementasyon detayları (ölçülmüş değerlere göre):**

- **Sliding window:** ~40 dakika, pencerede ~72 çağrı hakkı (ampirik olarak ölçüldü)
- **Hedefimiz:** 60 saniyede bir çağrı → saatte 60 çağrı, 40-dk pencerede 40 çağrı
- **Kullanım oranı:** Pencere kapasitesinin %56'sı (44 çağrı tampon)
- **Celery beat schedule:** `fetch_iett_fleet` her 60 saniyede bir
- **Redis sayaç:** Son 40 dakikadaki çağrı sayısı, 60'a ulaşırsa pause
- **Cooldown davranışı:** Rate limit ihlal edilirse ~30 dakika tamamen bloklu kalıyor — bu süre zarfında stale cache kullan, UI'da "Canlı veri gecikiyor" banner'ı göster
- **Distributed lock:** Prod'da birden fazla worker varsa sadece bir tanesi çağrı yapsın (Redis SETNX lock)
- **Stale cache TTL:** 5 dakika (normal) → 45 dakika (hata moduna geçilirse)
- **UI göstergesi:** "Son güncelleme: X saniye önce" — 90 saniyeyi geçerse sarı, 180 saniyeyi geçerse kırmızı

---

## 5. Mimari

### 5.1. Genel Mimari Şeması

```
┌─────────────────────────────────────────────────────────────────┐
│                    VERİ KAYNAKLARI (İBB)                         │
├──────────────────────┬──────────────────────┬──────────────────┤
│  İETT SOAP           │  Metro İstanbul REST │  GTFS statik     │
│  (canlı konum)       │  (tarife, istasyon)  │  (ZIP dosyaları) │
└──────────┬───────────┴──────────┬───────────┴────────┬─────────┘
           │                       │                    │
           ▼                       ▼                    ▼
┌─────────────────────────────────────────────────────────────────┐
│             ADAPTÖR KATMANI (Celery Workers)                     │
│  • SOAP→JSON dönüşümü (zeep)                                     │
│  • Normalize edilmiş "VehiclePosition" formatına çevirme         │
│  • Rate limiting, retry, cache                                   │
└──────────┬──────────────────────────────────────────┬───────────┘
           │                                           │
           ▼                                           ▼
┌──────────────────────────────┐    ┌───────────────────────────────┐
│  PostgreSQL + PostGIS        │    │  Redis                         │
│  • GTFS statik veri           │    │  • Mapping cache (günlük)      │
│  • Hatlar, duraklar, rotalar  │    │  • Hat bazlı snapshot'lar      │
│  • Kullanıcılar (v1.1+)       │    │    (vehicles:route:{short_name})│
│                               │    │  • Hat bazlı pub/sub kanalları │
│                               │    │  • Channel layer (Channels)    │
└──────────┬───────────────────┘    └──────────┬────────────────────┘
           │                                    │
           ▼                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                        DJANGO BACKEND                            │
├──────────────────────┬──────────────────────┬──────────────────┤
│  REST API            │  Django Channels     │  Admin Panel     │
│  (DRF)               │  (WebSocket)         │                  │
│  • /api/routes/      │  • /ws/vehicles/     │  • GTFS yönetim  │
│  • /api/stops/       │  • Canlı konum push  │  • Durak/hat CRUD │
│  • /api/trips/       │                      │  • Log görüntüleme│
└──────────┬───────────┴──────────┬───────────┴──────────────────┘
           │                       │
           │ HTTP (statik veri)    │ WebSocket (canlı veri)
           ▼                       ▼
┌─────────────────────────────────────────────────────────────────┐
│                      FRONTEND (Browser)                          │
├──────────────────────────────────────────────────────────────────┤
│  MapLibre GL JS (harita motoru, 3D binalar, terrain)            │
│  Three.js (araç 3D geometrileri)                                 │
│  deck.gl (büyük veri katmanları, hat çizgileri)                  │
│  Vanilla JS / TypeScript (uygulama mantığı)                      │
│  i18next (TR/EN çeviri)                                          │
└──────────────────────────────────────────────────────────────────┘
```

### 5.2. Teknoloji Seçimleri ve Gerekçeler

| Katman | Teknoloji | Gerekçe |
|---|---|---|
| Dil (backend) | Python 3.11+ | Django, zeep (SOAP), gtfs-kit kütüphaneleri için |
| Framework | Django 5.x | Geliştiricinin deneyimi, GeoDjango, admin paneli, DRF ekosistemi |
| API | Django REST Framework | Standart, stabil, dokümantasyon güzel |
| WebSocket | Django Channels 4.x | Django içinde kalmak, ayrı Node.js kurulmasın |
| ASGI server | Daphne (geliştirme), Uvicorn (production) | Channels uyumu |
| Veritabanı | PostgreSQL 16 + PostGIS 3.4 | Mekansal sorgular, GTFS ile doğal uyum |
| Cache / Pub-sub | Redis 7.x | Channels backend, Celery broker, response cache |
| Task queue | Celery 5.x + Redis broker | Periyodik SOAP çağrıları için |
| Periyodik görevler | django-celery-beat | Admin panelinden yönetilebilir zamanlayıcı |
| SOAP client | zeep | Python'da standart SOAP kütüphanesi |
| GTFS parsing | gtfs-kit | GTFS ZIP okuma, validasyon |
| Frontend dil | TypeScript | Tip güvenliği, agent'ın daha az hata yapması |
| Frontend build | Vite | Hızlı, modern, Django static ile uyumlu |
| Harita motoru | MapLibre GL JS 5.x | Açık kaynak Mapbox fork, 3D terrain desteği |
| 3D | Three.js (MapLibre custom layer ile) | Mini Tokyo 3D yaklaşımı |
| Veri görselleştirme | deck.gl | Binlerce araç render için GPU kullanır |
| Harita tile'ları | OpenFreeMap | Tamamen ücretsiz, API key yok |
| DEM / terrain | Mapterhorn | Ücretsiz raster-DEM |
| Test | pytest (backend), Vitest (frontend) | Modern, hızlı |
| Code quality | ruff, black, eslint, prettier | Opinionated, agent için iyi |

### 5.3. Ortak Veri Formatı: `VehiclePosition`

Farklı kaynaklardan gelen verileri tek bir forma normalize ediyoruz. Bu, GTFS-Realtime `VehiclePosition` mesajından esinleniyor ama daha basit:

```python
# backend/realtime/schemas.py
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class VehiclePosition(BaseModel):
    vehicle_id: str           # "C-231" (İETT kapı no) veya "M2-T-042"
    route_id: str             # "15B" veya "M2"
    trip_id: Optional[str]    # GTFS trip_id, eşleşirse
    latitude: float
    longitude: float
    bearing: Optional[float]  # Yön derecesi (0-360), hesaplanabilir
    speed: Optional[float]    # km/h, ölçülebilirse
    timestamp: datetime
    source: str               # "iett-soap", "simulated-metro", "simulated-ferry"
    mode: str                 # "bus", "metro", "marmaray", "tram", "funicular", "ferry"
```

**Frontend WebSocket mesaj formatı (JSON):**

Hat-merkezli model gereği her hat için ayrı update mesajı gider. Frontend sadece izlediği hatların mesajını işler, toplu büyük payload çözmek zorunda kalmaz.

```json
// Her hat için ayrı mesaj, 60sn'de bir (hat başına)
{
  "type": "route_vehicles_update",
  "route_id": "29B",
  "timestamp": "2026-04-19T14:23:45Z",
  "vehicles": [
    {
      "id": "C-231",
      "lat": 41.04885,
      "lon": 29.10322,
      "bearing": 87.5,
      "speed": 24.0
    }
  ]
}
```

Detaylı pub/sub ve cache stratejisi §5.7'de.

### 5.4. Tarife-Bazlı Simülasyon (Metro, Marmaray, Vapur)

Canlı konum verisi olmayan modlar için **client-side simülasyon** yapıyoruz:

1. **Sunucu tarafı:** GTFS `stop_times.txt` veriyi yükler, her trip için durak-zaman çiftlerini veritabanına koyar.
2. **API:** `/api/trips/active/?mode=metro&time=now` — şu anda aktif olan tripleri ve durak geçiş zamanlarını döner.
3. **İstemci tarafı:** Her trip için, şu anki zamana göre durak A ile durak B arasında interpolasyon yapar:
   - `stop_times.txt`'den: durak A'dan 14:23:00'de çıktı, durak B'ye 14:25:30'da varıyor
   - `shapes.txt`'den: A ile B arası geometri (polyline)
   - Şu an 14:24:15 ise: yolun %50'sinde, bu konumu polyline üzerinde hesapla
4. **Animasyon:** `requestAnimationFrame` ile sürekli yeniden hesapla

Bu yaklaşım Mini Tokyo 3D'nin ana mekanizmasıdır. Canlı veri yokken bile "hareketli" hissi verir. Tabii gerçek gecikmeleri yansıtmaz, o yüzden UI'da bir "Simulated" badge gösterelim.

**Simülasyon için kritik veri:** `shapes.txt` hat geometrileri olmazsa simülasyon düz çizgiyle ilerler (çirkin görünür). İBB GTFS paketinde shapes varsa kullan, yoksa duraklar arası OSM'den yol çekmemiz gerekir (karmaşık, Faz 5'te ele al).

### 5.5. 3D Sahne Stratejisi

**Görsel Yaklaşım: Esnek mimari, A'dan başla B'ye geliş**

**İlk sürümde (v1.0):**
- **Base map:** OpenFreeMap "bright" veya "positron" stili
- **3D binalar:** MapLibre `fill-extrusion` layer'ı, OpenStreetMap'in `building` tag'inden gelen yükseklik/kat bilgisiyle
- **3D terrain:** Mapterhorn DEM ile, Boğaz kenarları, Çamlıca Tepesi, Pierre Loti, Galata bölgesi gibi topografyalar otomatik yükselir
- **Landmark'lar:** OSM'de ne tag varsa o render edilir. Ayasofya, Galata Kulesi gibi yapılar OSM'de detaylı mappe edilmişse kubbe/kule olarak görünür; değilse generic extrusion olarak görünür. Biz data-side iyileştirme yapmayız, render-side'da ne varsa gösteririz.
- **Su yüzeyleri:** Boğaz, Haliç, Marmara Denizi OSM'den otomatik alınır, özel mavi renklendirilir
- **Araçlar:** Three.js `BoxGeometry` ile basit kutular. Her mod için renk kodu:
  - Otobüs: İETT kırmızı (#E40521)
  - Metro hattı rengi (M1A sarı, M2 yeşil, M3 mavi, vb. — gerçek kurumsal renkler)
  - Marmaray: mavi-beyaz
  - Tramvay: İETT tramvay mavisi
  - Vapur: kırmızı-beyaz

**Sonraki sürümlerde (v1.4+):**
- Landmark 3D modelleri (manuel GeoJSON + `extrude` özel property'si ile)
- Araç geometrileri daha detaylı (otobüs silueti, metro vagonu)
- Gelişmiş terrain shader'ları

### 5.6. Geliştirme Ortamı

**Geliştirici makinesinde çalıştırma:**

Docker kullanmıyoruz (tercih üzere). Aşağıdaki servisler yerel olarak çalışır:

1. **PostgreSQL 16 + PostGIS** — yerel kurulum (Homebrew, apt, Windows installer)
2. **Redis 7** — yerel kurulum
3. **Django geliştirme sunucusu** — `python manage.py runserver 8000`
4. **Django Channels ASGI** — `daphne -p 8001 config.asgi:application`
5. **Celery worker** — `celery -A config worker -l INFO`
6. **Celery beat** — `celery -A config beat -l INFO`
7. **Frontend dev sunucusu** — `npm run dev` (Vite, port 5173)

**Port haritası:**

| Port | Servis | Notlar |
|---|---|---|
| 8000 | Django HTTP (runserver) | REST API, admin |
| 8001 | Daphne ASGI | WebSocket endpoint'i `/ws/` |
| 5173 | Vite dev server | Frontend |
| 5432 | PostgreSQL | Varsayılan |
| 6379 | Redis | Varsayılan |

> **⚠️ GELİŞTİRME ORTAMI KURULUM UYARISI (Antigravity agent dikkatine):**
> Bu proje yeni bir makine üzerinde kurulurken **yeni bir PostgreSQL veritabanı**
> (`mini_istanbul_dev`) oluşturulmalı ve yukarıdaki portların **kullanılabilir**
> olduğundan emin olunmalıdır. Port 8001 ve 5173 diğer projeler tarafından
> kullanılıyorsa `.env` dosyasında değiştirin. Kurulum adımlarının tamamı bu
> dokümanın 8. bölümünde (Kurulum Kılavuzu) listelenmiştir.

**Frontend proxy ayarı:** Vite dev server, `/api/*` ve `/ws/*` isteklerini Django'ya proxy'ler (CORS derdi yok):

```js
// frontend/vite.config.ts
server: {
  proxy: {
    '/api': 'http://localhost:8000',
    '/ws': { target: 'ws://localhost:8001', ws: true }
  }
}
```

### 5.7. Hat-Merkezli Pipeline

UI modeli hat-merkezli olduğu için (§3.3), pipeline'ın son aşaması veriyi araç bazlıdan hat bazlına dönüştürür. Upstream'den gelen ham veri hâlâ araç granülerliğinde (her araç ayrı kayıt) — bu değişmedi, değişmiyor. Değişen tek şey fetch task'ının son adımı.

**Not: `route_id` semantikleri.** `VehiclePosition.route_id` field'ı (bkz. §5.3) şema seviyesinde değişmedi, ama içine atanan değer artık GTFS'in `routes.route_id` primary key'i değil, hattın **`short_name` değeridir** (ör. `"29B"`, `"M2"`, `"34BZ"`). Kanal isimlendirmesi, Redis key'leri ve WebSocket subscribe'ı hepsi bu değere bağlı. Gerekçe §3.3'te (DB row ≠ fiziksel hat, kullanıcı short_name ile mental model kuruyor).

#### Veri akışı (60 saniyelik tick)

```
1. adapter.fetch() → list[VehiclePosition]         # ~6900 araç, route_id=None
2. Mapping cache'ten her araç için route_id set et  # KapiNo + timestamp → SHATKODU
                                                    # route_id = short_name
3. defaultdict(list) ile hat bazlı grupla           # {"29B": [...], "34BZ": [...]}
4. Her hat için iki Redis işlemi:
   a. SET vehicles:route:{short_name} = JSON (TTL 120 sn)  ← son snapshot cache
   b. PUBLISH vehicles:route:{short_name} = JSON           ← WebSocket trigger
```

Çıkan sonuç: 6.900 araç fetch'i → ~800-1.000 aktif hat key'ine ve pub mesajına dönüşür (metrobüs + normal otobüs, günlük aktif set). Sürekli görünür raylı/vapur kategorileri (metro/tram/fun/marmaray/vapur = ~121 unique short_name) bu pipeline'a dahil değil — onlar canlı veri taşımıyor, Faz 5 tarife simülasyonuyla ayrı işleniyor. Redis trafik artışı kabul edilebilir (her değer 1-20 kayıt, ortalama ~4 KB).

#### Mapping cache formatı

Günlük refresh task (`refresh_iett_mapping`) `GetIettArsivGorev_json(yesterday)` çağırır, sonucu tek Redis key'inde JSON olarak tutar:

```json
{
  "date": "2026-04-22",
  "by_kapi": {
    "A-231": [
      {"start_ms": 1776863726000, "end_ms": 1776868886000,
       "hat": "29B", "guzergah": "29B_G_D0"},
      {"start_ms": 1776870000000, "end_ms": 1776875000000,
       "hat": "15B", "guzergah": "15B_D_D0"}
    ],
    "A-232": [...]
  },
  "active_routes": ["29B", "34BZ", "15B", ...],
  "routes_by_mode": {
    "metrobus": ["34", "34A", "34AS", "34B", "34BZ", "34C", "34G", "34T", "34Z", "34U"],
    "bus":      ["29B", "15B", "36T", ...]
  }
}
```

`hat` ve `active_routes` değerleri `SHATKODU`'dan gelir ve `short_name` namespace'iyle eşleştirilir. `routes_by_mode` kategorileri §3.3'teki tespit mekanizmasına göre hesaplanır (metrobüs whitelist match'i, kalan İETT hatları "bus"). Raylı sistem ve vapur kategorileri İETT feed'inde olmadığından bu mapping'de görünmez — onların routes listesi GTFS DB'den doğrudan okunur (`/api/routes/active/` endpoint'i iki kaynağı birleştirir).

Tek key (~2-3 MB JSON), her fetch task'ında bir `GET` + bir parse, ~10-30ms overhead. Tüm fetch worker'ları aynı cache'i okur, `refresh_iett_mapping` task günde bir kez güncelleyip atomik `SET` yapar (tutarlılık sorunu yok).

**Lookup algoritması** (`route_id` enrichment): araç için `by_kapi[KapiNo]` listesini al, araç timestamp'ini her interval'in `[start_ms, end_ms]` aralığıyla karşılaştır. Liste zaman-sıralı olduğu için binary search (`bisect`) kullanılır, O(log n). Eşleşme bulunamazsa (görev arası boşluk, veya mapping eksik) araç `route_id=None` ile geçer, fetch task UI göstermez ama sayacı ("unmapped vehicles") admin panele yansır.

**Mapping ↔ DB hizalaması — doğrulandı (Faz 2 Adım 5b-ii, 2026-04-24).** Yesterday dump'ının (55.682 kayıt, 2026-04-22) unique `SHATKODU` set'iyle DB `Route.short_name` set'i karşılaştırıldı:

- **Intersection %95.6** (754 hat hem mapping'de hem DB'de) — hizalama iyi, mapping formatında normalization katmanına gerek yok
- **Mapping-only (orphan) 35 hat** — tamamı Türkçe karakterli sub-variant kodları (`11CÜ`, `15ÇK`, `AND1S` gibi). Upper/lower/strip normalization %0 kurtarma verdi; gerçek DB yokluğu (GTFS feed'inde yayınlanmıyorlar). Frontend'de `/api/routes/active/` bu orphan'ları `category: "unknown"` altında gösterebilir (Faz 3 kararı), polyline gelmeyeceği için subscribe'da uyarı verilir
- **DB-only (mapping'de yok) 833 hat** — 12 metro + 4 tram + 3 fun + 3 marmaray + 99 ferry + 710 normal bus + 2 metrobüs. Raylı/vapur beklenen (canlı veri yok). 710 normal bus dün servise girmemiş opt-in hatlar. İki metrobüs (`34T`, `34U`) beklenmez — admin panelde coverage alert'i 5f'te eklenir
- **10 inverted interval** dropped — `build_mapping()` warn+skip davranışı doğru, İETT dispatch UI'si elle düzeltme bug'ı sonucu

Sonuç: **Mapping formatı sabit, Redis'e yazılacak JSON `build_mapping()` çıktısıyla birebir.**

#### Pub/sub kanal modeli

Her hat bağımsız bir Redis channel: `vehicles:route:{short_name}`. Frontend bir hatta abone olduğunda Django Channels consumer o Redis channel'ına subscribe olur ve gelen mesajları client'a push eder.

**Neden hat bazlı kanallar?**
- **Performans:** Frontend 5 hat izliyorsa 5 hat mesajı alır — 1.000 hat değil
- **Bandwidth:** Her hat update'i 1-20 araçlık küçük payload (<10 KB), büyük toplu snapshot değil
- **UX:** Metrobüs hareketi akıcı kalır otobüs paneli kullanılmazken; frontend hat başına bağımsız interpolation state yönetir
- **Backend basitliği:** Consumer "hangi group'a mesaj göndereceğini" short_name ile seçer, bbox veya mode filtresi yapmak zorunda değil

#### Fetch task'ı hata modunda ne olur?

1. **Rate limit BLOCKED/COOLDOWN:** Adapter boş liste döner. Fetch task Redis'te var olan snapshot'lara dokunmaz — TTL 120sn geçtiyse kaybolurlar, geçmediyse frontend stale cache'ten okur. Admin panelde "son başarılı fetch 180sn önce" sarı→kırmızı uyarı göstergesi.
2. **Parser hatası:** Kayıt bazlı skip (summary log'da sayılır), başarılı kayıtlar yine pub edilir.
3. **Mapping cache eksik:** `route_id=None` ile geçen araç fetch task'ta gruplama dışında kalır (hangi hat'a ait olduğu bilinmiyor). Admin panelde "unmapped" sayacı. Ertesi gün 04:00'da mapping yenilenir, sorun sıfırlanır.


Detaylı implementasyon Faz 2 Adım 5'te (Celery wiring).

#### v0.8 pivot (2026-04-26)

UX pivot sonrası (tüm 6911 araç haritada ham nokta, hat filtresi
görsel) pipeline'ın son adımı sadeleştirildi. Hat-bazlı `SET
vehicles:route:{short_name}` + `PUBLISH` kombinasyonu yerine tek `SET
vehicles:all` + `channel_layer.group_send("vehicles_all", ...)` model
kullanılıyor.

Payload formatı (6c-i implementation, `apps.realtime.tasks.fetch_iett_positions`):

```json
{
  "type": "vehicles_all_update",
  "timestamp": "2026-04-26T08:30:00Z",
  "vehicle_count": 6911,
  "mapped_count": 3320,
  "vehicles": [
    {"id": "C-231", "lat": 41.04, "lon": 29.10, "bearing": 87.5,
     "speed": 24.0, "route_id": "29B"},
    {"id": "C-232", "lat": 41.05, "lon": 29.11, "bearing": null,
     "speed": null, "route_id": null}
  ]
}
```

`route_id null` = hat bilinmiyor (mapping eksik). UX pivot gereği bu
araçlar payload'da tutulur, frontend ham nokta olarak çizer, popup'ta
"hat bilinmiyor" notu gösterir. `mapped_count` payload'daki `route_id
!= null` vehicle sayısı, `vehicle_count` ise toplam — frontend HUD bu
iki değerle "mapped/total" oranını gösterir.

Hat-bazlı kanallar silinmedi — Faz 5'te metro/marmaray/vapur
simülasyonu eklendiğinde geri gelecek. O zaman her mod için ayrı
schedule kanalı (`trips:active:M2` gibi) ile birlikte hat-bazlı yapı
yeniden devreye girer ve §6.4'teki orijinal subscribe modeli o ihtiyaç
için revize edilir.

Şimdiki sade modelin gerekçesi: UX pivot sonrası kullanıcı zaten tüm
filoyu görüyor, server-side hat filtresi yapmaya değen bir ihtiyaç
yok. 800 fanout × 60sn yerine 1 fanout × 60sn — bandwidth sıkıştırma
sonrası sınırda ama yönetilebilir (~200KB/60sn/client).

---

## 6. Django Uygulama Yapısı

### 6.1. Proje Dizin Yapısı

```
mini-istanbul/
├── backend/
│   ├── config/                      # Django project settings
│   │   ├── __init__.py
│   │   ├── settings/
│   │   │   ├── base.py
│   │   │   ├── development.py
│   │   │   └── production.py
│   │   ├── urls.py
│   │   ├── asgi.py                  # Channels için
│   │   ├── wsgi.py
│   │   └── celery.py
│   │
│   ├── apps/
│   │   ├── gtfs/                    # Statik GTFS verileri
│   │   │   ├── models.py            # Agency, Route, Stop, Trip, StopTime, Shape
│   │   │   ├── admin.py
│   │   │   ├── serializers.py       # DRF
│   │   │   ├── views.py             # REST endpoints
│   │   │   ├── urls.py
│   │   │   └── management/
│   │   │       └── commands/
│   │   │           ├── import_gtfs.py    # GTFS ZIP → DB
│   │   │           └── download_gtfs.py  # İBB'den indir
│   │   │
│   │   ├── realtime/                # Canlı veri
│   │   │   ├── schemas.py           # Pydantic VehiclePosition
│   │   │   ├── adapters/
│   │   │   │   ├── iett_soap.py     # İETT SOAP wrapper
│   │   │   │   ├── metro_rest.py    # Metro İstanbul REST wrapper
│   │   │   │   └── base.py          # Ortak interface
│   │   │   ├── tasks.py             # Celery tasks
│   │   │   ├── consumers.py         # Channels WebSocket consumer
│   │   │   ├── routing.py           # WebSocket URL routing
│   │   │   └── publishers.py        # Redis pub/sub
│   │   │
│   │   └── core/                    # Ortak yardımcılar
│   │       ├── models.py            # Ortak abstract modeller
│   │       └── utils.py
│   │
│   ├── static/                      # Django static (admin vb.)
│   ├── templates/
│   ├── manage.py
│   ├── pyproject.toml               # Poetry ya da pip-tools
│   └── .env.example
│
├── frontend/
│   ├── src/
│   │   ├── main.ts                  # Giriş noktası
│   │   ├── map/
│   │   │   ├── MapController.ts     # MapLibre instance yönetimi
│   │   │   ├── layers/
│   │   │   │   ├── buildings3d.ts
│   │   │   │   ├── terrain.ts
│   │   │   │   ├── routes.ts        # Hat çizgileri (deck.gl)
│   │   │   │   └── vehicles.ts      # Three.js custom layer
│   │   │   └── styles/
│   │   │       └── istanbul-base.json
│   │   ├── data/
│   │   │   ├── api.ts               # REST API client
│   │   │   └── websocket.ts         # WebSocket client
│   │   ├── simulation/
│   │   │   └── interpolator.ts      # Tarife-bazlı simülasyon
│   │   ├── ui/
│   │   │   ├── StopPopup.ts
│   │   │   ├── RoutePanel.ts
│   │   │   └── LanguageSwitcher.ts
│   │   ├── i18n/
│   │   │   ├── tr.json
│   │   │   └── en.json
│   │   └── types/
│   │       └── index.ts             # Paylaşılan tipler
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts
│   └── tsconfig.json
│
├── docs/
│   ├── SETUP.md
│   ├── API.md
│   └── CONTRIBUTING.md
│
├── scripts/
│   └── initial-setup.sh             # DB oluştur, migrate, seed
│
├── .gitignore
├── README.md
└── LICENSE
```

### 6.2. Temel Django Modelleri (Özet)

Ayrıntılar için `docs/MODELS.md` (ayrıca yazılacak). Burada şema düzeyinde özet:

```python
# apps/gtfs/models.py (özet - tam hali farklı dosyada)

from django.contrib.gis.db import models

class Agency(models.Model):
    agency_id = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=200)
    url = models.URLField()
    timezone = models.CharField(max_length=50, default='Europe/Istanbul')
    lang = models.CharField(max_length=10, default='tr')

class Route(models.Model):
    ROUTE_TYPES = [
        (0, 'Tram'), (1, 'Subway'), (2, 'Rail'),
        (3, 'Bus'), (4, 'Ferry'), (6, 'Aerial'), (7, 'Funicular'),
    ]
    route_id = models.CharField(max_length=50, unique=True)
    agency = models.ForeignKey(Agency, on_delete=models.CASCADE)
    short_name = models.CharField(max_length=50)  # "M2", "15B"
    long_name = models.CharField(max_length=200)  # "Yenikapı - Hacıosman"
    route_type = models.IntegerField(choices=ROUTE_TYPES)
    color = models.CharField(max_length=7, default='#000000')  # #RRGGBB
    text_color = models.CharField(max_length=7, default='#FFFFFF')

class Stop(models.Model):
    stop_id = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=200)
    location = models.PointField(srid=4326)  # PostGIS
    location_type = models.IntegerField(default=0)  # 0=stop, 1=station, 2=entrance

class Shape(models.Model):
    """Hat geometrisi (simülasyon için kritik)"""
    shape_id = models.CharField(max_length=50, unique=True)
    geometry = models.LineStringField(srid=4326)

class Trip(models.Model):
    trip_id = models.CharField(max_length=100, unique=True)
    route = models.ForeignKey(Route, on_delete=models.CASCADE)
    shape = models.ForeignKey(Shape, null=True, on_delete=models.SET_NULL)
    headsign = models.CharField(max_length=200)
    direction_id = models.IntegerField(default=0)
    service_id = models.CharField(max_length=50)  # calendar.txt referansı

class StopTime(models.Model):
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name='stop_times')
    stop = models.ForeignKey(Stop, on_delete=models.CASCADE)
    arrival_time = models.DurationField()   # GTFS: HH:MM:SS, >24 olabilir
    departure_time = models.DurationField()
    stop_sequence = models.IntegerField()

    class Meta:
        ordering = ['trip', 'stop_sequence']
        indexes = [models.Index(fields=['trip', 'stop_sequence'])]
```

### 6.3. REST API Endpoint'leri

```
GET  /api/agencies/                    Tüm operatörler
GET  /api/routes/                      Tüm hatlar (pagination)
GET  /api/routes/?mode=bus             Filtreleme
GET  /api/routes/{route_id}/           Tek hat detayı (geometri dahil)
GET  /api/routes/{route_id}/stops/     Hatın durakları (sıralı)
GET  /api/routes/{route_id}/shape/     Hatın geometrisi (GeoJSON LineString)

# Hat-merkezli endpoint'ler (v0.7):
GET  /api/routes/active/               Bugün aktif hatlar + kategorileri.
                                       Response: {
                                         "categories": {
                                           "metro": ["M1A", "M2", ...],
                                           "tram": ["T1", ...],
                                           "funicular": ["F1", ...],
                                           "marmaray": ["MRM"],
                                           "metrobus": ["34", "34A", ...],
                                           "ferry": [...],
                                           "bus": ["29B", "15B", ...]
                                         },
                                         "total_active": 820,
                                         "refreshed_at": "2026-04-24T04:00:00Z"
                                       }
GET  /api/routes/active/?mode=metrobus Kategori filtresi
GET  /api/routes/{route_id}/live/      Tek hatın canlı araçları (snapshot)
                                       — frontend hat seçince ilk render için

GET  /api/stops/                       Tüm duraklar (pagination + bbox filtre)
GET  /api/stops/?bbox=28.9,41.0,29.1,41.1  Bbox içindeki duraklar
GET  /api/stops/{stop_id}/             Tek durak detayı
GET  /api/stops/{stop_id}/upcoming/    Yaklaşan araçlar (next N arrivals)

GET  /api/trips/active/                Şu an aktif tripler (tarife simülasyonu için)
GET  /api/trips/active/?mode=metro     Mod filtresi
GET  /api/trips/{trip_id}/             Trip detayı (stop_times dahil)

GET  /api/vehicles/live/               Tüm sistem snapshot (fallback, WebSocket yoksa)

WS   /ws/vehicles/                     Canlı araç konumları (WebSocket)
                                       Subscribe: { "action": "subscribe",
                                                    "route_ids": [...] }
                                       Detaylar §6.4'te.
```

### 6.4. WebSocket Protokolü

**v0.8 pivot (2026-04-26):** UX pivotu sonrası protokol sadeleştirildi.
Aşağıdaki orijinal hat-merkezli `subscribe`/`subscription_ack` modeli
Faz 5'e ertelendi (hat-bazlı simülasyon kanalları için kullanılacak).
Faz 3'te kullanılan sadeleştirilmiş model:

- Client `ws/vehicles/`'a bağlanır
- Sunucu hemen mevcut `vehicles:all` snapshot'ını gönderir (`type: "vehicles_all_update"`)
- Sonraki her 60sn'de yeni snapshot mesajı gelir (aynı type)
- "İlk render" ve "update" arasında semantik ayrım yok — tek tip, frontend mesajı geldikçe state'ini overwrite eder
- Client'tan server'a anlamlı mesaj sadece `{action: "ping"}` (server `{type: "pong"}` cevap verir)
- `subscribe`/`unsubscribe`/`subscription_ack` mesajları YOK
- Aynı IP'den max 5 eşzamanlı bağlantı (cap aşımı: close code 4008)

**REST fallback (Faz 3 6e):** WebSocket'a bağlanamayan client'lar
için `GET /api/vehicles/live/` endpoint'i son `vehicles:all`
snapshot'ını JSON olarak döner. Payload formatı WebSocket
mesajıyla birebir aynı (`vehicles_all_update` type, payload
örneği §5.7'de). Cache-Control max-age=60 (fetch task tick
aralığıyla uyumlu). Snapshot yoksa veya bozuksa 503 + retry-
friendly Cache-Control: no-store. Public endpoint, Faz 3
kapsamında auth yok; production rate limit Faz 6 polish.

Aşağıdaki orijinal protokol Faz 5'te metro/marmaray/vapur için
geri gelir.

---

#### Orijinal hat-merkezli protokol (Faz 5 için korundu, şu an inaktif)

> Aşağıdaki içerik Faz 3'te **kullanılmıyor**. Faz 5'te
> metro/marmaray/vapur simülasyonu eklendiğinde hat-bazlı kanal
> modeli geri gelecek; o zaman bu örnekler güncel kontrata revize
> edilir.

**Bağlantı:** `ws://localhost:8001/ws/vehicles/`

Hat-merkezli model gereği abonelik route_ids odaklı. Kullanıcı hangi hatları izliyorsa o hatların mesajını alır. Bbox filtresi desteklenir ama ikincil — çoğu kullanıcı sürekli-görünür sete ek olarak 1-5 hat seçer, bbox'a değil hat listesine göre filtrelenir.

**Client → Server mesajları:**

```json
// İzlemek istediğin hatları bildir. Her subscribe komutunda mevcut liste
// REPLACE edilir — delta değil, snapshot semantik. İki hat bırakmak
// isteyen client her iki hattın ID'sini de gönderir.
{
  "action": "subscribe",
  "route_ids": ["M2", "M7", "34BZ", "29B"],
  "bbox": [28.9, 40.9, 29.2, 41.2]  // opsiyonel, server-side tight filter için
}

// Tüm aboneliklerden çık (örn. harita açıkken sekme değiştirildi)
{
  "action": "unsubscribe_all"
}
```

**Server → Client mesajları:**

```json
// Her hat için ayrı update. Fetch task (60sn) yeni snapshot aldığında
// sadece abone olunan hatların mesajı gelir. Araç sayısı azsa küçük
// payload, çoksa sadece o hat için büyük — toplu big-bang yok.
{
  "type": "route_vehicles_update",
  "route_id": "29B",
  "timestamp": "2026-04-19T14:23:45Z",
  "vehicles": [
    {
      "id": "C-231",        // KapiNo
      "lat": 41.04885,
      "lon": 29.10322,
      "bearing": 87.5,      // hesaplanabilirse
      "speed": 24.0         // km/h, upstream'den geliyorsa
    }
  ]
}

// Hatta şu an araç yoksa da bir mesaj gelir (frontend stale göstermesin)
{
  "type": "route_vehicles_update",
  "route_id": "M2",
  "timestamp": "2026-04-19T14:23:45Z",
  "vehicles": []
}

// Sürekli görünür setteki simülasyon araçları için (Faz 5)
// — canlı veri yok, client-side tarife interpolation yapıyor, server
// sadece hangi trip'lerin aktif olduğunu söylüyor
{
  "type": "route_trips_active",
  "route_id": "M2",
  "timestamp": "2026-04-19T14:23:45Z",
  "trips": [
    {"trip_id": "M2_T_0001", "direction": 0, "shape_id": "..."}
  ]
}

// Hata
{
  "type": "error",
  "code": "UNKNOWN_ROUTE",
  "message": "route_id 'XXX' is not active today"
}

// Abonelik doğrulaması (client state sync için)
{
  "type": "subscription_ack",
  "route_ids": ["M2", "M7", "34BZ", "29B"],
  "rejected": []  // aktif olmayan ID'ler
}
```

---

## 7. Geliştirme Fazları (Iteration Plan)

Her faz **çalışır bir uygulama** çıkarır. Antigravity agent her faz sonunda durum kontrolü yapabilir.

### Faz 1: Veri Altyapısı (tahmini 2-3 hafta, tek kişi)

**Hedef:** Statik GTFS verisi PostGIS'te, admin panelinden görüntülenebilir, basit Leaflet haritada duraklar ve hatlar gösteriliyor.

**Çıktılar:**
- [x] Django projesi kurulmuş, PostgreSQL + PostGIS bağlı
- [x] `apps/gtfs/models.py` tamamlanmış, migrate edilmiş
- [x] `python manage.py download_gtfs` — İBB'den ZIP'leri indirir
- [x] `python manage.py import_gtfs` — ZIP → DB
- [x] Django admin'de Routes, Stops, Trips listelenebiliyor
- [x] `/api/routes/`, `/api/stops/` basit endpoint'leri çalışıyor
- [x] Basit bir Leaflet sayfası tüm durakları ve hatları gösteriyor (3D değil, sadece veri doğrulama için)

**Bitiş kriteri:** Haritaya baktığında İstanbul'un tüm durak ve hatları görünüyor; veri tutarlı.

### Faz 2: Canlı Veri Adaptörü (2-3 hafta)

**Hedef:** İETT SOAP servisinden canlı otobüs konumları alınıyor (60 saniyede bir), `KapiNo → HatKodu` enrichment sonrası hat bazlı Redis key'lerine yazılıyor, hat bazlı pub/sub ile WebSocket'e hazır. Admin panelinden sayı takip edilebiliyor.

**Adım 4 (tamamlandı 2026-04-24) — Adapter çekirdeği:**
- [x] `apps/realtime/adapters/iett_soap.py` — ham HTTP + string SOAP envelope (zeep WSDL parse edemiyor, bkz. Ek A.11.2)
  - `GetFiloAracKonum_json()` — tüm filo, ~6900 araç, ~1.1MB
  - `GetIettArsivGorev_json(Tarih)` (`ibb360.asmx`, bkz. Ek A.11.1) — günlük mapping
- [x] Pydantic şemalar: `VehiclePosition`, `IettArsivGorev`, `parse_msdate`
- [x] `BaseAdapter` soyut sınıfı
- [x] `SlidingWindowLimiter` (Redis ZSET tabanlı, 4 state: OK/WARNING/BLOCKED/COOLDOWN)
- [x] Distributed lock (Redis SETNX + Lua atomic release)
- [x] Fleet + arsiv parser'ları (summary log: non_T_status/null_start/null_end/malformed ayrımı)
- [x] Cassette-based test suite (43 test, 0.64s, canlı API'ye gitmiyor)

**Adım 5 (sırada) — Celery wiring + hat-merkezli pipeline:**
- [x] **5a. Discovery query** ✅ (2026-04-24): DB'deki 9.773 Route kaydının §3.3'teki kategorilere dağılımı ölçüldü. Unique short_name bazında: Metro 12, Tram 4, Fun 3, Marmaray 3, Metrobüs 10 (whitelist %100 match), Vapur ~99, Normal otobüs 1.080. Route_type 9 (minibus, 317 row) ve route_type 10 (taksi dolmuş, 58 row) GTFS extended — MVP kapsam dışı, v1.3'e ertelendi. T5 ve F4 İstanbul'da servis veriyor ama İBB feed'inde yok. Detaylar §3.3 tablosunda.
- [ ] **Mapping cache** (`refresh_iett_mapping` Celery task, günde 1 kez 04:00):
  - `fetch_arsiv_gorev(yesterday)` → Pydantic filtreleme
  - §5.7'deki JSON formatında Redis'e yaz (`iett:mapping:current` tek key, TTL 28 saat)
  - `by_kapi` + `active_routes` + `routes_by_mode` hesapla
- [ ] **Enrichment helper** (`apps/realtime/enrich.py`):
  - `enrich_with_route_id(vehicles, mapping)` — araç listesine `route_id` set et (değer = `SHATKODU` = `short_name`)
  - Binary search (bisect) ile O(log n) lookup per araç
  - Mapping eksik olan araç → `route_id=None`, sayacı artır
- [ ] **Fetch task** (`fetch_iett_positions` Celery task, 60sn beat):
  - `adapter.fetch()` → enrichment → `defaultdict(list)` groupby(route_id)  # route_id = short_name
  - Her hat için `SET vehicles:route:{short_name}` (TTL 120sn) + `PUBLISH vehicles:route:{short_name}`
  - Unmapped araç sayısı Redis sayacı (`stats:unmapped_count`)
  - Stale cache fallback: fetch fail olsa bile önceki snapshot TTL süresince kalır
- [ ] **Celery beat schedule** config'te:
  - `fetch_iett_positions` → every 60 seconds
  - `refresh_iett_mapping` → daily 04:00 UTC
- [ ] **Admin panel** "Live Vehicles" sayfası:
  - Son 60 saniyedeki toplam araç sayısı
  - Hat bazlı breakdown (en aktif 20 hat, araç sayısıyla)
  - Son çağrı timestamp'i
  - Son 40 dakikadaki çağrı sayısı (grafikle)
  - API health durumu (green/yellow/red)
  - Rate limit durumu ("44/72 — 28 hak kaldı")
  - Unmapped vehicle sayısı + yüzdesi
- [ ] Entegrasyon testleri: `test_enrichment.py`, `test_fetch_task.py`, `test_refresh_task.py`
- [ ] **Canlı smoke test** (Yağız onayıyla, kontrollü, tek çağrı)

**Bitiş kriteri:** `celery -A config worker` + `beat` çalışırken, 60 saniye sonra Redis CLI `SUBSCRIBE vehicles:route:*` dinleyince hat bazlı mesajlar akıyor. Admin panelinde 40dk pencere kullanım oranı %56 civarında (~40/72 çağrı), unmapped oran %5'in altında.

### Faz 3: WebSocket Katmanı (1-2 hafta)

**Hedef:** Redis'teki hat bazlı pub/sub mesajlarını WebSocket üzerinden tarayıcıya push eden bir katman. Hat-merkezli abonelik modeli.

**Çıktılar:**
- [ ] Django Channels kuruldu, Daphne port 8001 (ya da 8011, `.env`'den override'lanabilir)
- [ ] `apps/realtime/consumers.py` — `VehiclePositionConsumer`
  - Connect: anonim, aynı IP'den max 5 eşzamanlı bağlantı
  - `subscribe` action: `route_ids` listesi REPLACE semantiğiyle, opsiyonel bbox
  - Her `short_name` için Redis channel `vehicles:route:{short_name}`'a subscribe
  - Redis pub/sub → WebSocket group broadcast bridge
  - İlk abone olunca ilgili hatların son snapshot'ını (Redis `GET vehicles:route:{short_name}`) hemen gönder
  - `subscription_ack` mesajıyla aktif hat listesini doğrula (aktif olmayan ID'ler `rejected`'a düşer)
- [ ] `apps/realtime/routing.py` — `ws/vehicles/` URL path
- [ ] Fallback REST: `GET /api/vehicles/live/` (WebSocket kurulmazsa tüm sistem snapshot fallback)
- [ ] `GET /api/routes/{route_id}/live/` — tek hatın son snapshot'ı (frontend hat seçince ilk render için)
- [ ] `GET /api/routes/active/` — bugün aktif hatlar + kategorileri (mapping cache'ten)
- [ ] Rate limit per IP: aşırı `subscribe`/`unsubscribe` döngüsü throttle
- [ ] Basit Leaflet test sayfası: 3-4 hat seç → hareketli araçlar görünür

**Bitiş kriteri:** Django HTTP + Daphne + Celery worker + beat aynı anda çalışıyor. Browser DevTools → Network → WS: bağlantı 101 Switching Protocols. `subscribe` ile `["M2", "34BZ"]` gönder → sadece bu iki hat için `route_vehicles_update` mesajları geliyor. `subscribe ["M2"]` (yenile) → 34BZ akışı duruyor, M2 devam.

### Faz 4: 3D Frontend (3-4 hafta)

**Hedef:** MapLibre + Three.js ile 3D harita, hat-merkezli açılış (sürekli görünür kategoriler), hat filtreleme paneli, araçlar akıcı (60 FPS) hareket ediyor.

**Görünüm modeli (Tokyo vibes):**
- Açılışta haritada **sürekli görünür setin** polyline'ları çizilir, üstlerinde araçlar hareket eder
- Sağ panel: "Hatlar" sekmesi — arama kutusu + mod bazlı gruplar (Metro, Metrobüs, vapur, ...) + otobüs hat listesi (arama ile filtrelenir)
- Otobüs hatları opt-in: kullanıcı checkbox'la ekler → haritaya polyline + araçlar gelir, WebSocket subscribe
- Hat tıklanınca highlight, diğerleri sönükleşir (focus mode); tekrar tıklanınca toplu görünüme döner
- Araç tıklanınca popup: KapiNo, Plaka, hangi hatta, son hız

**Çıktılar:**
- [ ] Vite + TypeScript frontend kuruldu
- [ ] MapLibre GL JS ile OpenFreeMap stil yüklendi
- [ ] 3D binalar (`fill-extrusion`) aktif
- [ ] Mapterhorn terrain aktif
- [ ] Three.js custom layer (araçlar için)
- [ ] **Hat filtreleme paneli** (Faz 6'dan taşındı — MVP için kritik, bu olmadan otobüsler gösterilemez):
  - Sürekli görünür kategoriler açılışta seçili
  - Arama kutusu: "29B" yaz → o hat listede aşağı filtrelenir
  - Hat toggle: WebSocket `subscribe` / `unsubscribe` trigger
  - Seçili hat sayısı göstergesi (örn. "8 hat izleniyor")
- [ ] WebSocket client (`src/data/websocket.ts`):
  - Reconnect
  - Hat seçim değişikliklerinde `subscribe` mesajı gönder
  - Per-route `route_vehicles_update` mesajlarını hat state'lerine route et
- [ ] REST API client (`src/data/api.ts`):
  - `GET /api/routes/active/` → kategori listesi
  - `GET /api/routes/{route_id}/shape/` → hat polyline'ı (cache'lenir)
  - `GET /api/routes/{route_id}/live/` → hat seçilince ilk render için snapshot
- [ ] Three.js `InstancedMesh` araç render sistemi (GPU'da instancing)
- [ ] **Client-side interpolation (zorunlu, zira veri 60sn aralıklı):**
  - T₀ ve T₁ konumları arasında polyline-aware interpolasyon
  - Aracın hattının `shapes.txt` polyline'ına projekte et
  - Polyline üstünde lineer ilerleme, 60 FPS `requestAnimationFrame`
  - Edge case: polyline'dan sapma → düz çizgi fallback; shape yok (İETT otobüsleri için) → düz çizgi (Faz 5'te OSM snapping ile çözülür)
- [ ] Kamera kontrolleri (pitch, bearing, zoom limitleri)
- [ ] Durak tıklama → popup (yaklaşan araçlar)
- [ ] Hat tıklama → highlight + focus mode
- [ ] "Son güncelleme: X saniye önce" UI göstergesi (90sn sarı, 180sn kırmızı)

**Bitiş kriteri:** `npm run dev` + backend tüm process'leri çalışıyor. `localhost:5173` → İstanbul 3D haritası, metrobüs otobüsleri + metro/marmaray/vapur simüle araçları akıcı hareket ediyor. Sağ panelden "29B" seç → haritaya eklendi, kendi araçlarıyla. Seçimden çıkar → haritadan temizlendi. Kamera rotasyonu + 3D bina yükseklikleri Boğaz kenarında belirgin.

### Faz 5: Metro / Marmaray / Vapur Simülasyonu (2 hafta)

**Hedef:** Otobüs dışındaki modlar da hareketli.

**Çıktılar:**
- [ ] `/api/trips/active/` endpoint'i yazıldı
- [ ] Client-side `interpolator.ts` — `stop_times` + `shape` → konum
- [ ] Requestanimationframe loop ile sürekli güncelleme
- [ ] UI'da "Simulated" badge (canlı verisi olmayan araçlar için)
- [ ] Tüm modlar için farklı renkli geometri

**Bitiş kriteri:** Metro, Marmaray ve vapur araçları da haritada hareketli.

### Faz 6: Cilalama (süresiz, kontinü)

**Hedef:** Kullanıcı deneyimi, performans, i18n, mobil uyum.

**Çıktılar:**
- [ ] Türkçe / İngilizce dil değiştirici (i18next)
- [ ] Responsive tasarım (mobil breakpoint)
- [ ] Performans: görünür bbox dışındaki araçları gizle
- [ ] Durak arama (autocomplete)
- [ ] Hat filtreleme paneli
- [ ] Saat çubuğu (v2'ye ertelenebilir)
- [ ] Landmark özel GeoJSON (Ayasofya, Galata vb. — opsiyonel)
- [ ] Production deployment dokümanı

---

## 8. Kurulum Kılavuzu (Antigravity Agent için)

### 8.1. Ön Koşullar

Geliştirme makinesinde aşağıdakiler kurulu olmalı:

- **Python 3.11 veya üzeri** (`python3 --version` ile kontrol)
- **Node.js 20 LTS veya üzeri** (`node --version` ile kontrol)
- **PostgreSQL 16** (PostGIS eklentisi ile)
- **Redis 7.x**
- **Git**

Kurulu değilse (işletim sistemine göre):

```bash
# macOS (Homebrew)
brew install python@3.11 node@20 postgresql@16 redis
brew services start postgresql@16
brew services start redis

# Ubuntu / Debian
sudo apt update
sudo apt install python3.11 python3.11-venv python3-pip nodejs npm \
    postgresql-16 postgresql-16-postgis-3 redis-server

# Windows
# PostgreSQL: https://www.postgresql.org/download/windows/  (PostGIS Stack Builder ile)
# Redis: Microsoft Store'dan "Redis for Windows" ya da WSL içinde
# Python ve Node: python.org ve nodejs.org'dan
```

### 8.2. Veritabanı Kurulumu

> **⚠️ ÖNEMLİ: Yeni bir veritabanı oluşturuyoruz.**
> Bu projenin kendi izole veritabanı olmalı. Başka projelerin db'sini paylaşmıyoruz.

```bash
# PostgreSQL'e bağlan
sudo -u postgres psql   # Linux
psql postgres           # macOS Homebrew

-- Aşağıdakileri psql içinde çalıştır:
CREATE USER mini_istanbul WITH PASSWORD 'change_me_in_env';
CREATE DATABASE mini_istanbul_dev OWNER mini_istanbul;
\c mini_istanbul_dev
CREATE EXTENSION postgis;
CREATE EXTENSION postgis_topology;
\q
```

### 8.3. Proje Kurulumu

```bash
# 1. Repo'yu klonla
git clone https://github.com/yagizfirat/mini-istanbul-3d.git
cd mini-istanbul-3d

# 2. Backend virtualenv
cd backend
python3.11 -m venv venv
source venv/bin/activate        # Linux/macOS
# venv\Scripts\activate         # Windows PowerShell

pip install --upgrade pip
pip install -r requirements/development.txt

# 3. Environment dosyası
cp .env.example .env
# .env içinde şunları güncelle:
#   DATABASE_URL=postgres://mini_istanbul:change_me_in_env@localhost:5432/mini_istanbul_dev
#   REDIS_URL=redis://localhost:6379/0
#   SECRET_KEY=<yeni bir secret key, python -c "import secrets; print(secrets.token_urlsafe(50))">
#   DEBUG=True
#   ALLOWED_HOSTS=localhost,127.0.0.1

# 4. Migrate
python manage.py migrate

# 5. Superuser
python manage.py createsuperuser

# 6. GTFS verisini indir ve import et (15-30 dakika sürebilir)
python manage.py download_gtfs
python manage.py import_gtfs

# 7. Frontend bağımlılıkları
cd ../frontend
npm install
```

### 8.4. Çalıştırma

Beş ayrı terminal penceresi gerekiyor (ya da `tmux`, `screen`, vs.):

```bash
# Terminal 1: Django REST API
cd backend
source venv/bin/activate
python manage.py runserver 8000

# Terminal 2: Daphne WebSocket server
cd backend
source venv/bin/activate
daphne -p 8001 config.asgi:application

# Terminal 3: Celery worker (canlı veri adaptörü)
cd backend
source venv/bin/activate
celery -A config worker -l INFO

# Terminal 4: Celery beat (periyodik görevler)
cd backend
source venv/bin/activate
celery -A config beat -l INFO

# Terminal 5: Frontend dev server
cd frontend
npm run dev
```

Tarayıcıda `http://localhost:5173` adresine git.

### 8.5. Çalışma Sonrası Doğrulama

Her şey çalışıyorsa şunları görmelisin:

1. `http://localhost:5173` — İstanbul'un 3D haritası yükleniyor (Faz 4'ten sonra)
2. `http://localhost:8000/admin/` — Django admin, Routes/Stops listelenebiliyor
3. `http://localhost:8000/api/routes/` — JSON olarak hat listesi dönüyor
4. WebSocket: Chrome DevTools → Network → WS sekmesi → `ws://localhost:8001/ws/vehicles/` bağlantısı 101 Switching Protocols ile kurulmuş
5. Terminal 3 (Celery worker) loglarında: `Fetched X vehicles from IETT SOAP` mesajları

---

## 9. Test Stratejisi

### Backend
- **Unit testler (pytest):** Her model, her serializer, her adapter
- **Integration testler:** API endpoint'leri, WebSocket consumer'ları
- **Mock external APIs:** İETT SOAP ve Metro REST çağrıları `responses` ya da `vcr.py` ile kaydedilip replay edilir (canlı API'ye test sırasında gitmeyiz)

### Frontend
- **Unit testler (Vitest):** Interpolator, API client, WebSocket client
- **E2E:** Playwright (gelecek fazda — MVP'de opsiyonel)

### Hedef kapsama
- Backend: >80% line coverage
- Frontend: >60% line coverage (3D render tarafı zor)

---

## 10. Risk Analizi

| Risk | Etki | Azaltma Stratejisi |
|---|---|---|
| İETT rate limit (40dk/72 çağrı) aşılırsa | **Kritik** | 60sn aralıklı çağrı + Redis sliding window sayacı + distributed lock; 500 hata alınırsa 30 dakika pause |
| İETT SOAP servisi çökerse | Yüksek | Redis'te son bilinen konumu cache'le (TTL 45dk hata modunda), UI'da "Veri gecikmesi" uyarısı |
| SOAP endpoint'i değişirse / kapanırsa | Yüksek | Adaptör katmanı yüzünden sadece bir dosya değişir; fallback olarak ulasav.csb.gov.tr |
| Kapı no → hat eşlemesi bozulursa | Orta | Araç "unknown route" ile gösterilir, hata log'lanır, günlük re-fetch |
| GTFS formatı İBB'de güncellenirse | Orta | `gtfs-kit` validator + her import'ta log, şema değişikliklerini yakala |
| GTFS'te `shapes.txt` eksikse (hat için) | Orta | Duraklar arası düz çizgi fallback + Faz 6'da OSM'den route shape çekme. **Güncel ölçüm (2026-04-27, Faz 3 Adım 6h-ii canlı smoke):** İETT feed shape coverage **0/1096** short_name, public feed **496/496**. Canlı akıştaki spatial sanity check (`apps/realtime/spatial.py`, mapped vehicle ile route shape arası haversine, 500m threshold) cache miss durumunda mapping korunur (graceful skip), defansif null'lama yok. Public feed'in 496 shape'i cache'te hazır, Faz 5+ trip simülasyonunda etkin olur. |
| Performans: 6900+ araç aynı anda | Yüksek | Bbox filtresiyle sadece görünür araçlar, deck.gl GPU kullanımı, Three.js instancing |
| Client-side interpolation yanlış tahmin yapar | Düşük | Araç yol dışına çıkarsa 60sn sonraki veri düzeltir; UI'da "tahmini konum" badge (opsiyonel) |
| OSM'de bina verisi eksikse | Düşük | Generic extrusion yine gösterilir, Faz 6'da community mapping katkısı |
| Tarih/saat/zone bug'ları | Orta | Her şey UTC + Europe/Istanbul; Django TIME_ZONE = 'Europe/Istanbul', USE_TZ=True |
| Aşırı WebSocket bağlantısı (DOS benzeri) | Düşük | Rate limit per IP, anonymous için connection cap |
| İBB rate limit politikası değişirse | Orta | Ampirik testler periyodik tekrarlansın (3-6 ayda bir), strateji güncellensin |

---

## 11. Açık Sorular (Geliştirme Sırasında Karar Verilecek)

**Cevaplanan sorular (v0.1 ve v0.2'den):**
- ~~İETT SOAP endpoint URL'si nedir?~~ → **Cevaplandı:** `api.ibb.gov.tr/iett/FiloDurum/SeferGerceklesme.asmx`, WSDL bozuk ama ham SOAP çalışıyor
- ~~Rate limit var mı, ne kadar?~~ → **Cevaplandı:** 40 dakikalık sliding window, ~72 çağrı
- ~~API key gerekiyor mu?~~ → **Cevaplandı:** Gerekmiyor, anonim erişim açık
- ~~Backend refresh rate?~~ → **Cevaplandı:** Ortalama 60.3 saniye

**Geliştirme sırasında cevaplanacak:**

1. `GetFiloAracKonum_json()` dönen veride bazı araçların `Operator` değeri `OHO` olarak geliyor (Akyolbil dış operatörleri). Bunlar İETT hatları değil, özel halk otobüsleri olabilir. Nasıl sınıflandırılacaklar? (Faz 2'de data eksplorasyonu ile)
2. GTFS paketindeki `shapes.txt` tüm hatlar için mevcut mu, yoksa bazı hatlar için geometri eksik mi? (Faz 1'de test edilecek)
3. Metro İstanbul REST API'si authentication gerektiriyor mu? Rate limit var mı? Ayrı mı İETT SOAP ile paylaşımlı mı? (Faz 1-2 arası test edilecek — **önemli:** İETT test scripti Metro İstanbul API için de uyarlanıp çalıştırılmalı)
4. Marmaray ve İDO GTFS paketleri ayrı mı yoksa "Genel Toplu Ulaşım GTFS" içinde birleşik mi? (Faz 1'de keşfedilecek)
5. `GetIettArsivGorev_json(Tarih)` bugünkü tarih için çalışıyor mu yoksa sadece geçmiş için mi? (Faz 2'de test edilecek — kapı no → hat eşlemesinin temelini oluşturuyor)
6. İETT'nin "güzergah kodu" kavramı GTFS'teki `shape_id` veya `direction_id`'ye nasıl eşleşiyor? (Faz 1'de veri incelemesi)
7. Diğer İETT SOAP servisleri (Duyurular, PlanlananSeferSaati, vb.) SeferGerceklesme ile rate limit paylaşımlı mı, bağımsız mı? Test et.
8. Landmark 3D modellerini hangi lisansla nereden alacağız? (Faz 6'da kararlaştırılır — Sketchfab CC0, manuel GeoJSON, Blender modeling)

---

## 12. Lisanslama

- **Kod lisansı:** MIT
- **Veri lisansı:**
  - İBB açık veri: İstanbul Büyükşehir Belediyesi Açık Veri Lisansı (attribution gerekli)
  - OpenStreetMap: ODbL (attribution gerekli, türev eserler ODbL olmalı)
  - OpenFreeMap: Attribution gerekli (MapLibre otomatik ekliyor)
  - Mapterhorn DEM: Attribution gerekli
- **Attribution metni (uygulamada görünecek):**
  > Veri: © İstanbul Büyükşehir Belediyesi, © OpenStreetMap katkıda bulunanlar
  > Harita: © OpenFreeMap © OpenMapTiles
  > Arazi: © Mapterhorn

---

## 13. Referanslar

**Ana referanslar:**
- **İETT Web Servis Kullanım Dokümanı v1.5 (İBB resmi PDF):** [pdf link](https://data.ibb.gov.tr/dataset/3e32bb5d-2936-41eb-bdc7-65b843487e99/resource/6821f452-f6ff-49e9-940a-d4ebfc78f03e/download/iett-web-servis-kullanm-dokumanv.1.2.pdf) — **KESİN KAYNAK, İETT API için primary reference**
- **Mini Tokyo 3D:** https://github.com/nagix/mini-tokyo-3d (mimari ilham kaynağı)
- **Mini Tokyo 3D live:** https://minitokyo3d.com/
- **İBB Açık Veri Portalı:** https://data.ibb.gov.tr/

**Standartlar:**
- **GTFS spec:** https://gtfs.org/schedule/reference/
- **GTFS-Realtime spec:** https://gtfs.org/realtime/reference/

**Teknoloji dokümantasyonu:**
- **MapLibre GL JS:** https://maplibre.org/maplibre-gl-js/docs/
- **OpenFreeMap:** https://openfreemap.org/
- **Django Channels:** https://channels.readthedocs.io/
- **Celery periodic tasks:** https://docs.celeryproject.org/en/stable/userguide/periodic-tasks.html

**Veri kümeleri:**
- **İETT GTFS veri seti:** https://data.ibb.gov.tr/dataset/iett-gtfs-verisi
- **Genel Toplu Ulaşım GTFS:** https://data.ibb.gov.tr/dataset/public-transport-gtfs-data

**Community projeleri (referans, dependency değil):**
- **hakanatak/dataibbgovtr_python:** https://github.com/hakanatak/dataibbgovtr_python
- **İETT SOAP kullanım örneği:** https://burakbayramli.github.io/dersblog/sk/2023/01/iett-ibb-otobus-verisi.html
- **AydinAdn/IBB.Api (.NET):** https://github.com/AydinAdn/IBB.Api

**Proje ampirik testleri (v0.3 için yapıldı):**
- `test_ibb_token_v2.py` — Token uyumluluğu testi
- `test_rate_limit.py` — Rate limit dayanıklılık testi (fast/long modes)
- `test_29b_tracking.py` — Araç hareket takibi + cooldown testi
- `test_refresh_rate.py` — Backend refresh rate ölçümü

---

## Ek A: Veri Gerçekliği Bulguları

Faz 1 geliştirmesi sırasında İBB verisinin gerçekte ne durumda olduğu ampirik olarak ortaya çıktı. Bu bulgular implementasyon kararlarını şekillendirdi ve Faz 2+ için referans olarak burada kayıt altına alınıyor.

### A.1 Format tutarsızlığı

İETT ve Public dataset'leri farklı ekiplerden derlenmiş:

- İETT: UTF-8 with BOM + semicolon delimiter (GTFS spec virgül ister)
- Public: cp1254 (Windows Turkish) + comma delimiter

Sonuç: `gtfs-kit` kullanılamaz, ham `pandas.read_csv` + auto-detect encoding/delimiter gerekli. Her CSV dosyası için ayrı tespit yapılır çünkü aynı dataset içinde bile dosyalar farklı encoding kullanabilir.

### A.2 Koordinat bozulması — Excel Turkish locale

İETT stops.csv'deki ~15.378 satırda koordinatlar Excel'de açılıp kaydedilince Turkish thousand-separator (nokta) artifact'i oluşmuş:

`410.191.700.005.564` → gerçekte `41.0191700005564`

Çözüm: `_sanitize_coord()` ilk noktayı koru, diğerlerini sil, sonra float'a çevir. Recovery oranı: %99.9 (3 satır corrupt kaldı, skip).

### A.3 Route_id 118-way collision

Public (Mart 2024) ve İETT (Mart 2026) feed'leri **aynı route_id**'yi tamamen farklı hatlara atamış. Örnek:

- Public `1296` = M1A Metro (Yenikapı-Atatürk Havalimanı)
- İETT `1296` = 19E Otobüs (Yenidoğan-İmes Camii)

Toplamda 118 çakışma. Bunların 7'si metro hattı (M1A, M1B, M2, M3, M4, T4, TF1) — İETT upsert ile overwrite edilince shape'leri ve renkleri kaybolacaktı.

Çözüm: route_id'ye feed prefix (`public:1296`, `iett:1296`). Sonuç: Route sayısı 9655 → 9773 (+118).

### A.4 İETT hat geometrisi yok

İETT'nin GTFS dataset'inde `shapes.csv` bulunmuyor. Yani İETT otobüsleri için hat güzergahı İBB tarafından yayınlanmıyor.

- Faz 1 MVP: duraklar arası düz çizgi (görünüm bozuk ama çalışır)
- Faz 5+: OSM Overpass API'den route snapping (pgr_dijkstra)

### A.5 İBB CKAN dataset şeması

Her iki dataset de 6-8 loose CSV olarak sunuluyor. İETT dataset'inde `stop_times.zip` adlı bir resource var — bu tam GTFS bundle **değil**, sadece büyük stop_times.csv'nin gzip'li halidir. Yanıltıcı.

### A.6 Küçük veri kalitesi sorunları

- `stop_lat` kolonuna timestamp, `stop_desc`, direction label sızmış (4 satır İETT)
- Public routes.csv'de 1 satır embedded comma ile 104-char route_id üretmiş (malformed)
- İETT routes.csv'de 4 intra-file duplicate route_id
- 451 trip'in direction_id'si NaN
- BOM olması encoding'in UTF-8 olduğunu garanti etmiyor (iki aşamalı doğrulama şart)

### A.7 İstanbul bbox (kalibre edilmiş)

- `lat_min = 40.7` (Gebze'nin güneyi)
- `lat_max = 41.5` (Yalıköy/Kırklareli sınırı — İETT kırsal hatlar)
- `lon_min = 27.95` (Silivri batısı, Binkılıç/Hallaçlı köyleri)
- `lon_max = 29.95` (Şile ÇELEBİKÖY)

### A.8 shape_pt_sequence int sort

Sequence kolonu `dtype=str` ile okunuyor, lexicographic sort `"1","10","11","2"...` üretiyor → polyline zigzag. `pd.to_numeric` ile int'e çevirmek şart.

### A.9 İETT SOAP canlı veri rate limit (ampirik)

- ~40 dakikalık sliding window
- ~72 çağrı/pencere hard limit
- ~30 dakika cooldown ihlal durumunda
- Backend refresh rate: ~60 saniye ortalama (min 57.1, max 68.1)
- Auth: anonim (CKAN token SOAP'ta etkisiz)

Strateji: 60sn server poll + client-side interpolation.

### A.10 Pandas NaN → 'nan' string tuzağı (route color)

`read_csv(na_values=[""])` + `dtype=str` → boş hücre `float('nan')`, `str(nan) = "nan"` (truthy string). `'or ""'` zincirine düşmez, DB'ye `'#NAN'` yazılır. SVG `stroke="#NAN"` geçersiz → polyline görünmez ama Leaflet `addLayer` çağrısı gerçekleştiği için "N hat çizildi" sayacı yanıltıcı.

Çözüm: `_clean_hex()` regex-validated 6-char hex; else default. Frontend `HEX_RE` guard defense-in-depth + turuncu fallback sayacı. Etkilenen: 498 public route color + 498 text_color (aynı satırlar). İETT etkilenmedi (bkz. ek gözlem).

**Ek gözlem — İBB renk metadata'sı hiç yayınlanmıyor:**

- public/routes.csv: `route_color` + `route_text_color` kolonları header'da VAR ama tüm 499 satırda boş.
- iett/routes.csv: `route_color`/`route_text_color` kolonları header'da YOK.

Yani İBB feed'leri hat renklerini hiçbir zaman publish etmiyor. Faz 4'te 3D harita için renk kodlaması elde-yazılı bir map gerekecek: `short_name → hex` (M1A, M2, M3, ..., Marmaray, T1-T5, F1-F4 — Metro İstanbul ve İETT kurumsal renkleri). Fallback siyah/gri.

### A.11 İETT SOAP gerçek yüzeyi — WSDL discovery

Spec §4.2.1'de varsayılan endpoint davranışı WSDL discovery testiyle (2026-04-23) doğrulandı ve iki ciddi hata ortaya çıktı:

**A.11.1 GetIettArsivGorev_json mevcut, ama farklı endpoint'te.** İlk varsayım metodun `SeferGerceklesme.asmx`'te olmasıydı (spec eski versiyonlarında böyle yazıldığı için). 2026-04-23 ampirik testi: `SeferGerceklesme.asmx`'e yapılan SOAP çağrısı HTTP 500 "Policy Falsified / Service Not Found" döndü — metot o endpoint'te yok. WSDL taraması doğruladı: `SeferGerceklesme.asmx` sadece 6 operation expose ediyor:

- `GetBozukSatih_XML` / `GetBozukSatih_json`
- `GetFiloAracKonum_json`
- `GetHatOtoKonum_json`
- `GetKazaLokasyon_XML` / `GetKazaLokasyon_json`

"ArsivGorev" bu listede yok. Çözüm İBB resmi web servis dokümanından (PDF §10.1) geldi: metot `ibb360.asmx` endpoint'inde tanımlı, full URL `https://api.ibb.gov.tr/iett/ibb/ibb360.asmx`. Dünün tarihiyle tek atış test (2026-04-23 21:07): HTTP 200, SOAP envelope temiz, 55.682 kayıt döndü (detay A.13, A.14). **Ders:** WSDL discovery'de "metot yok" sonucuna varmadan önce tüm ilgili endpoint'lerin WSDL'leri taranmalı — bir endpoint'teki yokluk başka endpoint'te yokluk demek değil. Zeep hâlâ İETT WSDL'lerini parse edemiyor (binding tanımları nedeniyle); ham `requests` + string SOAP envelope yaklaşımı Faz 2 için de geçerli.

**A.11.2 WSDL "broken" değil.** Spec §4.2.1'de "WSDL broken, zeep parse edemiyor" notu var. Ham HTTP GET ile WSDL 28 KB XML olarak 200 OK dönüyor, regex ile operation/message parse edilebiliyor. zeep'in parse edememesi kütüphane-seviyesi strict mode uyumsuzluğu, WSDL-seviyesi bozukluk değil. "Broken" ifadesi yanıltıcı, "zeep-incompatible" daha doğru.

**A.11.3 GetHatOtoKonum_json keşfi.** İlk planlamada fark edilmeyen bir method. İmza:

- Input: `<HatKodu>` string
- Output: JSON string (o hatta çalışan araçların listesi)

Ters yönde (HatKodu → araçlar) çalışıyor, bizim istediğimizin tersi (KapiNo → HatKodu). Brute force mapping için 9.300 hat × 72 çağrı/40dk rate limit = 86 saat, uygulanamaz. Yan ürün olarak Faz 3+'te "hat seçildi, sadece o hattın araçlarını göster" için kullanılabilir.

### A.12 GetFiloAracKonum_json field yüzeyi — spec §5.3 doğrulandı

Ampirik test (2026-04-23): 6.911 aracın konum response'unda hat identifier'ı YOK. Her aracın 8 field'ı var:

- `KapiNo`, `Plaka`, `Boylam`, `Enlem`, `Hiz`, `Saat`, `Garaj`, `Operator`

15 candidate key (HatKodu, HatNo, RouteCode, Guzergah vs.) test edildi, hiçbiri yok. Raw string probe da negatif — nested JSON içinde saklı değil.

Spec §5.3'teki "hat kodu YOK, sadece KapiNo" ifadesi doğrulandı, ama "günlük eşleme tablosu için GetIettArsivGorev_json çağrılır" önerisi çöktü (Ek A.11). Faz 2 mimarisinde alternatif yol gerekiyor.

### A.13 ibb360.asmx::GetIettArsivGorev_json — intra-day boş, günlük batch yazılıyor

Ampirik bulgu (2026-04-23): Bugünün tarihi (`20260423`) için metot boş array (`[]`, 2 byte) döndü. Aynı gün ayrı çağrıda dünün tarihi (`20260422`) için 55.682 kayıt geldi. İki rakip hipotez:

- **H1 (tatil kaynaklı):** Bugün resmi tatil (23 Nisan — Ulusal Egemenlik ve Çocuk Bayramı), İETT görev akışı azaldı/durdu. Arşivin canlı yazımı var ama bugün yazılacak iş yok.
- **H2 (günlük batch):** Servis intra-day yazmıyor, arşiv tablosu günlük batch ile (muhtemelen gece) dolar. Bugünün tarihi ertesi gün sabaha kadar boş görünür.

Hangisinin doğru olduğunu ayırt etmek için başka bir iş günü sabahında ek test gerekir. Şimdi kritik değil; gerek duyulursa Faz 2 başlangıcında yapılır.

**Pratik sonuç:** Mapping çağrısı günlük, "dün" tarihiyle yapılmalı. Response Redis'e cache'lenir, bugünün canlı `KapiNo`'larına uygulanır. TTL 26-28 saat (yarın yenilenince eski otomatik silinir).

**Risk:** Pazartesi sabahı Cuma'nın mapping'i kullanılır (hafta sonu servisin yazdığı, hafta içi garaj dağıtımından farklı olabilecek kayıtlar). Hafta sonu + Pazartesi sabah davranışı Faz 2 canlı izlemesinde doğrulanmalı.

### A.14 KapiNo → HatKodu 1:1 değil, zaman aralıklı görev listesi

Ampirik dağılım (2026-04-22 dünün verisi): **6.212 araç, 799 hat, 55.682 görev.** Araç başına ortalama ~9 görev/gün — tek araç gün içinde birden fazla hatta atanıyor. Dolayısıyla `KapiNo → HatKodu` doğrudan 1:1 dict olamaz; zaman-bağımlı lookup gerekir.

Response'un kritik field'ları:

- `SKAPINUMARA` — araç kapı no
- `SHATKODU` — hat kodu (ana granülerlik)
- `SGUZERGAHKODU` — hat + yön + varyant (örn. `15SK_G_D0`, format: `{HatKodu}_{Yön}_{Varyant}`). `G`=Gidiş, `D`=Dönüş tahmin ediliyor — doğrulama Faz 2'de GTFS `trips` tablosuyla join ederek yapılır.
- `DTBASLAMAZAMANI`, `DTBITISZAMANI` — görev zaman aralığı
- `SGOREVDURUM` — dağılım: `T` (%95.2), `I` (%3.9), `YK` (%0.7), `B` (%0.14). Kodların anlamı PDF'te tanımsız; tahmini açılım: `T`=Tamamlandı, `I`=İptal, `YK`/`B` belirsiz. Güvenli yaklaşım: **sadece `SGOREVDURUM = "T"` kayıtları mapping'e al.** Kalan %5 gürültü olarak değerlendirilir.

**Tarih formatı:** `/Date(1776863726000)/` — Microsoft JSON Date, epoch milisaniye. Python'da: `re.search(r"/Date\((\d+)\)/", v).group(1)` → `datetime.fromtimestamp(ms / 1000)`.

**Mimari sonuç:** Redis cache yapısı düz dict değil, her araç için zaman aralıklı görev listesi:

```
iett:mapping:{KapiNo} → [
  {start: epoch_ms, end: epoch_ms, hat: "15SK", guzergah: "15SK_G_D0"},
  ...
]
```

`GetFiloAracKonum_json`'dan gelen araç saati ile liste üzerinde binary search → aktif görevi bul → `HatKodu`/`GuzergahKodu` al.

**`SGUZERGAHKODU` → GTFS `shape_id` eşlemesi:** Faz 4 interpolation için kritik. Bir araç sadece "15SK hattında" değil, "15SK Gidiş yönünde D0 varyantında" olarak bilinirse, doğru shape polyline'ına projekte edilebilir. §11'deki 6. açık soru ("İETT güzergah kodu GTFS'te neye eşleşir?") muhtemelen buradan çözülür — Faz 2'de GTFS `trips` tablosuyla join doğrulanmalı.

**Cache boyutu:** Dünün tam dump'ı 24 MB (JSON). Sadece gerekli field'lar extract edilerek (`SKAPINUMARA`, `SHATKODU`, `SGUZERGAHKODU`, `DTBASLAMAZAMANI`, `DTBITISZAMANI` + `T` filtresi) ~5-8 MB'a inebilir.

---

### A.15 Vehicle.timestamp drift — fleet endpoint stale konum davranışı

Ampirik bulgu (2026-05-02): İETT `GetFiloAracKonum_json` idle/parked vehicle'lar için multi-hour-old `DTGUNCELLEMESAATI` dönüyor. Diagnostic histogram (n=56 out-of-interval-but-mapped, snap_sec=45844): bimodal dağılım, %7 taze (0-30s), %62 uç drift (>600s), gri bant 121-300s pratik olarak boş (1 vaka). Max gap 25618s (~7 saat).

**Mekanizma:** `enrich_with_route_id` `v.timestamp` ile bisect yapıyor. Stale timestamp eski interval'i buluyor → out-of-date PK stamp. Bisect kodu doğru, girdisi (`v.timestamp`) güvenilmez. Cross-check: 56/56 vakada `v.timestamp` ile bisect aktif interval buluyor, enrich'te branch sürprizi yok.

**Karşı-tedbir:** enrich'e `reference_now` opsiyonel param + 180s `abs` threshold. Fetch task `_utcnow()` ile besler, drift > 180s ise `route_id=None` + heartbeat counter `stats:stale_vehicle_dropped_count` incr. Threshold 180s = 3× nominal 60s tick, 0-180s mikro band'ı koruma altında.

**Live measurement** (Faz 2 5j-ii): tick başına ~150 vehicle drop. Yağız'ın gözleminin görünmez kısmı buradaydı — out-of-interval (56) sadece bayatlamış yarısı, interval-içi-ama-bayatlamış (~90) ek olarak temizlendi.

**Yapısal sınır:** bu filter "vehicle.timestamp drift" sınıfını eler, "arşiv stale'liği" (mapping geçen Cumartesi'nin görevini bugüne uyguluyor) sınıfını elemez. İkincisi için spatial doğrulama gerekir; İETT GTFS shape 0/1096 ve stop_times coverage 139/9274 olduğundan OSM Overpass + pgrouting gereklidir (Faz 5.5 planlı).

---

### A.16 İETT GTFS stop_times coverage — 139/9274 (~%1.5)

Ampirik bulgu (2026-05-02): Spec Ek A.4 İETT'nin `shapes.csv`'sinin yayınlanmadığını not ediyordu (shape coverage 0/1096). Ama 5j-ii ön-keşfinde mekansal motor için alternatif veri kaynağı (durak-bazlı polyline türetme) değerlendirildi. Sonuç: **stop_times coverage da büyük ölçüde eksik.**

Ölçüm: 4 SQL sorgusuyla `agency_id='1' AND route_type=3` filtresinde DB durumu çıkarıldı.

**Sorgu 1 (route coverage):** 9.274 İETT otobüs hattının 516 `route_id` kaydı için en az bir StopTime mevcut. İlk bakışta %5.56 görünür ama bu **DB row sayısıdır, fiziksel hat sayısı değil** — Faz 1'de feed-bazlı `route_id` prefix politikası gereği her short_name için ortalama ~8 row var.

**Sorgu 6 (unique short_name coverage):** Coverage'lı hatların unique short_name kümesi **139** (Sorgu 6 `total_with_coverage`). Yani 9.274 fiziksel hattan sadece ~%1.5'i için stop_times verisi var. Metrobüs hatlarının (34, 34A, 34BZ, 34G, vb.) **hiçbiri** kapsamda değil (`metrobus_covered=0`); 29B, 15B, 500T, 28T gibi popüler hatlar da kapsam dışı. Sorgu 5'in ilk 20'sinde 132M, 130Ş, 12A, 10, 142F, 131T, 142, 131YS, 11H, 133KT pattern'i — **130-134 ve 140-142 prefix'li bölgesel küme**. Coğrafi olarak Avrupa yakası kuzey-batı tahmini (Eyüp/Alibeyköy/Sultangazi); rastgele dağılım değil, yapısal feed eksikliği.

**Sorgu 2 (trip-içi stop dolgu):** 135.625 İETT trip'in 116.691'i (~%86) boş, 1.009'u 6-20 stop arası, 17.923'ü (~%13) 20+ stop'a sahip. Yani kapsam dahilindeki trip'ler kalitesiz değil — 18 bin trip 20+ durakla doldurulmuş, mediyan o kümede 30-40 civarı tahmini.

**Sorgu 3 (stop koordinatları):** Kapsam dahilindeki 5.909 unique stop'un %100'ü geçerli ve İstanbul bbox içinde. NULL veya out-of-bbox sıfır. Veri olduğunda temiz, bozuk değil.

**Sorgu 4 (trip dizilimi tutarlılığı):** Top 20 hat-direction çiftinde `variation_pct` %0.3-3.1 — hatların trip'leri tutarlı stop dizilimine sahip. Polyline cache'i hat-direction granülerliğinde yapılabilir, variant patlaması yok.

**Spatial motor değerlendirmesi:** Mapping günlük ~530-790 aktif hat üretirken kapsam sadece 139 — en iyi ihtimalle aktif setin %20'si spatial check ile doğrulanabilir. Üstelik metrobüs ve popüler otobüsler kapsam dışı, yani kullanıcının en çok dikkatini çeken araçlar için spatial doğrulama yok. B senaryosu (durak yakınlık + polyline kontrolü) maliyet/fayda dengesi zayıf.

**Sonuç:** İETT için kapsamlı spatial doğrulama yapısal olarak GTFS verisinden yapılamaz. Faz 5.5 (OSM Overpass + pgrouting) tek tam çözüm. Ara çözüm olarak 5j-ii drift filter denendi ve "vehicle.timestamp eski → eski interval'i bulup stamp ediyor" sınıfını eledi (~150 vehicle/tick), ama yapısal arşiv stale'liği (mapping geçen iş gününün görevini bugüne uyguluyor) için OSM yine zorunlu.

---

## 14. Doküman Versiyon Geçmişi

| Versiyon | Tarih | Değişiklik |
|---|---|---|
| 0.1 | 2026-04-19 | İlk taslak |
| 0.2 | 2026-04-19 | İETT resmi web servis dokümanı incelendi, rate limit keşfedildi (PDF'te "saatte 100" yazıyor), 3 strateji seçeneği eklendi |
| 0.3 | 2026-04-19 | Ampirik testler yapıldı: rate limit'in ~40dk/72 çağrı sliding window olduğu ölçüldü, backend refresh rate'in 60s olduğu doğrulandı, token'ın SOAP'ta etkisiz olduğu gösterildi. 3 seçenek kaldırıldı, **60 saniye aralıklı çağrı + client-side interpolation** kesinleştirildi |
| 0.4 | 2026-04-22 | Ek A eklendi: Faz 1 geliştirmesinde ortaya çıkan 10 maddelik ampirik veri kalitesi bulguları. route_id collision, Excel Turkish locale coord artifact, NaN→'nan' color trap, İBB'nin renk metadata yayınlamaması dahil. |
| 0.5 | 2026-04-23 | Faz 1.5 pre-flight WSDL discovery: GetIettArsivGorev_json metodunun mevcut olmadığı, WSDL'in aslında okunabilir olduğu ve GetHatOtoKonum_json'un yeni keşfi Ek A'ya (A.11) eklendi. Faz 2 mimarisi kapı no → hat kodu eşleme kaynağı bekliyor. |
| 0.6 | 2026-04-23 | Ek A.12 eklendi: GetFiloAracKonum_json response'unda hat identifier olmadığı doğrulandı. KapiNo → HatKodu eşleme için API seçeneği kalmadı. Faz 2 öncesi İBB PDF incelenecek + GTFS heuristic değerlendirilecek. |
| 0.6.1 | 2026-04-23 | Ek A.11 düzeltildi (endpoint yanlış varsayımıydı — metot `ibb360.asmx`'te mevcut ve çalışıyor, dünün tarihi için 55.682 kayıt test edildi). A.13 (refresh pattern: intra-day boş, günlük batch), A.14 (zaman-bağımlı mapping, SGUZERGAHKODU granülerliği) eklendi. |
| 0.7 | 2026-04-24 | **UI modeli değişimi: araç-merkezli → hat-merkezli.** Kullanıcı bireysel araç değil, hat izler. Sürekli görünür kategoriler (metro/tramvay/füniküler/Marmaray/metrobüs/vapur) açılışta haritada; otobüs hatları opt-in. Yeni bölümler: §3.3 (mod sınıflandırması, metrobüs whitelist), §5.7 (hat-merkezli pipeline, cache stratejisi, pub/sub kanal modeli). Güncellenmiş: §5.3 (WebSocket mesaj formatı per-route), §6.3 (yeni endpoint'ler `/api/routes/active/` ve `/api/routes/{id}/live/`), §6.4 (subscribe `route_ids` odaklı), §7 Faz 2/3/4 (hat filtreleme UI MVP'ye taşındı). Yeni US-9 (hat izleme). Pipeline çekirdeği (adapter, rate limiter, lock, parser'lar — Faz 2 Adım 4'te tamamlandı) değişmedi. |
| 0.7.1 | 2026-04-24 | **§3.3 tablosu ampirik verilerle dolduruldu** (Faz 2 Adım 5a discovery query, 9.773 Route snapshot). Unique short_name sayıları: Metro 12, Tram 4, Fun 3, Marmaray 3, Metrobüs 10, Vapur ~99, Normal otobüs 1.080. Toplam sürekli görünür 131 unique hat. T5 ve F4 feed'de yok (İstanbul'da servis veriyor ama İBB yayınlamıyor) — belgelendi. Marmaray tespit filter'ı `agency_id=2 AND route_type=2` olarak netleşti (long_name match yanlış pozitif veriyordu). Route_type 9 (Minibus, 317 row) ve route_type 10 (Taksi Dolmus, 58 row) MVP kapsam dışı — v1.3'e ertelendi. **Kanal granülerliği `short_name` olarak sabitlendi** (`route_id` değil): Redis channel `vehicles:route:{short_name}`, `VehiclePosition.route_id` field'ı şema olarak korundu ama değeri artık `SHATKODU=short_name`. §5.7 mapping ↔ DB hizalama riski (SHATKODU set ∩ Route.short_name set) 5b'de doğrulanacak. |
| 0.7.2 | 2026-04-24 | **§5.7 mapping ↔ DB alignment sonucu eklendi** (Faz 2 Adım 5b-ii). 55.682 kayıtlık dump üzerinde ölçüldü: intersection %95.6 (754 hat hem mapping'de hem DB'de). Orphan 35 hat — tümü Türkçe karakterli sub-variant kodları (`11CÜ`, `15ÇK`, `AND1S` gibi), normalization %0 kurtarma verdi; mapping formatı değişmedi. DB-only 833 hat kategorize edildi: raylı/vapur (121) + opt-in henüz servise girmemiş (710) + 2 metrobüs (`34T`, `34U` — dün aktif olmamış). 10 inverted interval dropped. `build_mapping()` çıktısı Redis'e yazılacak final şema. |
| 0.7.3 | 2026-04-27 | **Faz 3 tamamlandı + spatial sanity check eklendi** (Adım 6h-i/ii/iii). `apps/realtime/spatial.py` modülü: lazy-load shape cache, numpy vectorized haversine, 500m threshold ile mapped vehicle'ın GTFS shape geometrisinden uzaklaşmış olanlarını `route_id=None`'a degrade eder. Canlı smoke İETT GTFS feed shape coverage **0/1096** short_name, public feed **496/496** olduğunu ortaya çıkardı (§10 Risk tablosu güncellendi). Cache miss durumunda graceful skip davranışı: mapping korunur, defansif null yok. Public feed'in 496 shape'i cache'te kalır, Faz 5+ trip simülasyonunda etkin olur. 7 commit zinciri: 6h-i `fcf1451`/`bc0d5f4`/`b8603d5`/`a07026b` (modül + entegrasyon + 7 test, 147 → 154), 6h-ii `2224e9e`/`c04d01e`/`a316df9` (graceful skip fix + docs + regression test, 154 → 155). Smoke 3 tick: `mapped_count≈1850`, `spatial_check.skipped_no_shape≈input` (beklenen, İETT shape'siz), `nullified_off_route=0`. Realtime suite 155/155 yeşil. |
| 0.7.4 | 2026-05-02 | **Yol B (vehicle.route_id GTFS PK semantics) + stale vehicle.timestamp filter** eklendi. Backend `enrich_with_route_id` artık SHATKODU short_name yerine canonical Route.route_id PK'sını stamp ediyor (`build_mapping` `route_id_by_short_name` index'i β filtresi `agency=IETT, route_type=3` + alfabetik tie-breaker ile üretir). Frontend RouteStore'a bus PK'ları `registerSummaries` ile yüklendi (Faz 6 KM1 reliquat). 5j-ii: out-of-interval-but-mapped vakası teşhisi, drift hipotezi cross-check ile A doğrulandı, `STALE_VEHICLE_TIMESTAMP_THRESHOLD_S=180` filter ve `stats:stale_vehicle_dropped_count` heartbeat counter eklendi. 5j-ii ön-keşfinde İETT stop_times coverage 139/9274 ölçüldü (Ek A.16). Yeni Ek A.15 (fleet endpoint stale konum davranışı) ve Ek A.16 (stop_times coverage). Realtime suite 165/165, frontend 210/210 yeşil. |
