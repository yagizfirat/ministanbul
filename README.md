# Mini İstanbul

İstanbul'un toplu taşıma ağını gerçek zamanlı, üç boyutlu bir harita üzerinde gösteren web uygulaması. Otobüsler, metrolar, Marmaray, vapurlar, tramvay ve füniküler — hepsi aynı haritada, kendi konumlarında, kendi rotalarında.

[Mini Tokyo 3D](https://github.com/nagix/mini-tokyo-3d)'in İstanbul versiyonu olarak başladı. Kişisel bir öğrenme projesi; yaklaşık iki ay sürdü.

**Canlı demo:** [ministanbul.yagizfirat.com](https://ministanbul.yagizfirat.com)


## Ne yapar

Harita üzerinde anlık olarak şunları görürsünüz:

- **Otobüsler** — İETT'nin kendi SOAP API'sinden 60 saniyede bir çekilen yaklaşık 6.900 araç pozisyonu. Hat bilgisiyle eşleşmiş olanlar renkli, eşleşmeyenler antrasit (metrobüs).
- **Metro, Marmaray, vapur, tramvay, füniküler** — Bu modlar için canlı veri kaynağı yok; GTFS tarifesinden simüle ediliyor. Yani harita üstünde gördüğünüz Marmaray treni o anda gerçekten o pozisyonda olmayabilir, ama tarifesi öyle diyor.
- **Hat çizgileri ve duraklar** — Bir hatta çift tıklayınca o hat odaklanır, kamera o bölgeye uçar, durakları ve sonraki istasyon bilgileri görünür.

Filtre paneliyle hangi modların görüneceğini açıp kapatabilir, URL üzerinden paylaşılabilir görünümler oluşturabilirsiniz (`?routes=M2,M4&bus=on` gibi).

## Niye yapıldı

İstanbul'un kamuya açık ulaşım verisi var ama insanların kullanabileceği güzel bir görselleştirme yoktu. Mini Tokyo 3D'yi gördüğümde "bu İstanbul için de yapılır" diye düşündüm — ve İstanbul'un veri kaynaklarının Tokyo'nunkilerden çok daha kırık, eksik ve dağınık olduğunu zaman içinde öğrendim. Projenin asıl ilginç kısmı bu kırıklıklarla baş etmek oldu.

## Nasıl yapıldı

Proje yedi fazda ilerledi. Her fazın sonunda çalışan bir şey vardı, bir sonraki fazın üzerine bunu kuruyordum.

**Faz 1 — Veri altyapısı (Nisan 2026):** İki ayrı GTFS feed'inin (İETT 9.300 hat + Public Transport metro/Marmaray/vapur) Django modellerine indirilmesi. İETT feed'inin UTF-8-BOM ve noktalı virgül ayraçlı olması, Public Transport feed'inin cp1254 encoded olması — encoding tespit ve dönüşüm. Yaklaşık 6.35 milyon `stop_time` satırının PostgreSQL'e bulk insert'lenmesi. PostGIS ile mekânsal sorgular.

**Faz 2 — Canlı veri adaptörü:** İETT'nin SOAP servisinden filo pozisyonu çekme. `zeep` kütüphanesi WSDL'i parse edemediği için ham `requests` ile XML üretme/okuma. Rate limit (yaklaşık 40 dakika pencere / 72 çağrı) keşfi ve adapte edilmesi. Celery beat ile 60 saniyede bir periyodik fetch.

**Faz 3 — WebSocket katmanı:** Django Channels + Daphne. Celery'nin yazdığı pozisyon güncellemelerinin Redis pub/sub üzerinden bağlı tüm istemcilere fan-out edilmesi. Cloudflare WARP'in 100 saniye idle timeout'u için ping/pong altyapısı.

**Faz 4 — 3D frontend:** Vanilla TypeScript + MapLibre GL JS. Three.js'i MapLibre'in custom layer API'sine bağlayan adaptör. OpenFreeMap vector tile'ları, Mapterhorn DEM ile arazi yükseltmesi. Vite build. Framework yok — sade DOM API ve modüler TS.

**Faz 5 — Raylı ve vapur simülasyonu:** Metro/Marmaray/vapur için canlı veri olmadığından, GTFS tarifesi üzerinden anlık pozisyon üretme. Trip'in `stop_time` zincirinde "şu an saat 14:32, bu trip 14:25'te kalktı, sıradaki durak 14:35'te" → durak A ile durak B arasında zamana göre lineer interpolasyon, shape geometrisi üzerinde projeksiyon.

**Faz 5.5 — Public Transit Refresh (Mayıs başı):** Otobüs realtime mapping katmanının (KapiNo → hat eşlemesi) sistematik olarak doğru çalışmadığının fark edilmesi. Üç günlük teşhis turu, 11 araştırma raporu (`_research/` klasöründe), %53 yanlış eşleşme oranının kanıtlanması. Kararı: otobüs bireysel hat eşlemesini emekliye ayırmak, metrobüsü ayrı görsel kategori olarak tutmak. Otobüs bir araç hangi hatta olduğunu söylemeden konumunu gösterir; metrobüs zaten kapalı bir koridorda olduğu için bunu bilmek gerekmez.

**Faz 6 — UX cilalama:** Bilinen bug'ların kapatılması, bundle size optimizasyonu (1066KB → 38KB app bundle, vendor split sayesinde), URL state persistence, mobil responsive (768px breakpoint, hamburger menü, bottom sheet), viewport-aware rendering (low-zoom'da nokta render, perf koruması).

**Faz 7 — Yayın:** Açık kaynak hazırlığı (lisans, secret tarama, dokümantasyon), production deployment (PostgreSQL+PostGIS+Redis kurulumu, dört systemd servisi, Nginx + Let's Encrypt, rate limiting, backup cron), canlıya çıkış.

Toplamda 312 frontend (Vitest) + 219 backend (pytest) = 531 yeşil test geride bıraktı.

## Mimari özet

| Katman | Teknoloji |
|---|---|
| Backend | Python 3.11+ / Django 5.1 / DRF |
| WebSocket | Django Channels 4 + Daphne |
| Veritabanı | PostgreSQL 16 + PostGIS 3.6 |
| Cache & broker | Redis 7 |
| Task queue | Celery 5 + django-celery-beat |
| Frontend | Vanilla TypeScript + Vite |
| Harita | MapLibre GL JS 5 |
| 3D | Three.js (MapLibre custom layer) |
| Tile | OpenFreeMap (vector) |
| Arazi | Mapterhorn DEM |
| Test | pytest + Vitest |

Production'da dört systemd servisi yan yana çalışır: gunicorn (HTTP), Daphne (WebSocket), Celery worker, Celery beat. Nginx önde reverse proxy.

## Veri kaynakları

- **İETT GTFS** — İBB Açık Veri portalı (`iett-gtfs-verisi`). Yaklaşık 9.300 otobüs hattı, 15.400 durak.
- **Public Transport GTFS** — İBB Açık Veri portalı (`public-transport-gtfs-data`). Metro, Marmaray, vapur, tramvay, füniküler.
- **İETT canlı filo** — `api.ibb.gov.tr/iett/FiloDurum/SeferGerceklesme.asmx`, `GetFiloAracKonum_json` metodu. Anonim erişim, rate limited.

Metro İstanbul'un REST API'si var ama canlı tren konumu döndürmüyor; tarife döndürüyor. Marmaray ve vapurlar için kamuya açık canlı veri yok.

## Hızlı başlangıç (geliştirici)

Detaylı kurulum (PostgreSQL+PostGIS, Redis, GTFS import, frontend build) ayrı bir doküman olabilir; aşağısı kafaya kabaca fikir versin diye:

```bash
# Backend
cd backend
python -m venv .venv && .venv/Scripts/activate  # veya source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py download_gtfs
python manage.py runserver

# Frontend
cd frontend
npm install
npm run dev

# Realtime (ayrı terminallerde)
celery -A config worker -l info
celery -A config beat -l info
daphne -b 0.0.0.0 -p 8001 config.asgi:application
```

`.env.example` dosyasını `.env`'e kopyalayıp doldurmanız gerekir.

## Proje yapısı

```
backend/      Django uygulaması (gtfs, realtime, api)
frontend/     Vite + TypeScript + MapLibre
data/         GTFS indirme hedefi (gitignored)
scripts/      Yardımcı script'ler
docs/         README görselleri
_research/    Geliştirme sırasında yazılan teknik teşhis raporları
```

`_research/` klasörü projenin sıkıntılı kararlarını ve teşhis süreçlerini olduğu gibi tutar — özellikle otobüs mapping'inin %53 yanlış olduğunu kanıtlayan üç günlük araştırma turu (Faz 5.5). Açık kaynak projelerin nadiren yaptığı bir şeydir bunu paylaşmak; ama gelecekte bu alanda çalışacak biri için doğrudan değerli bilgi olduğu için duruyor.

## Lisans

MIT. Detay için [LICENSE](./LICENSE).

**Veri lisansları (uygulama içi attribution):**
- © İstanbul Büyükşehir Belediyesi Açık Veri Lisansı
- © OpenStreetMap katkıda bulunanlar (ODbL)
- © OpenFreeMap, © OpenMapTiles
- © Mapterhorn

## Teşekkürler

[Mini Tokyo 3D](https://github.com/nagix/mini-tokyo-3d) — Akihiko Kusanagi'nin projesi. Bu proje doğrudan onun ilhamıyla başladı; pek çok UX kararı (sonraki durak gösterimi, hat odaklama, filtre paneli mantığı) oradan referans alındı.

İBB Açık Veri ekibi — Veri olmasa proje olmazdı.

MapLibre, OpenFreeMap, Mapterhorn, Three.js, Django ve Channels topluluklarının emeği için.
