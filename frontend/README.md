# Mini Istanbul 3D — Frontend

Vite + TypeScript + MapLibre GL JS. Faz 4 KM3.

## Geliştirme

`scripts\start_stack.bat` çift tıkla → 5 pencere açılır
(Django/Daphne/Worker/Beat/Vite). Tarayıcı: http://localhost:5173

Memurai zaten Windows servisi, ayrı başlatma yok.

İlk sefer Vite bağımlılıkları için:

```bash
cd frontend
npm install
```

## Backend bağımlılığı

`npm run dev` öncesi şunlar ayakta olmalı:

- Django HTTP — `localhost:8010` (REST: `/api/vehicles/live/`)
- Daphne ASGI — `localhost:8011` (WS: `/ws/vehicles/`)
- Celery worker + beat (60sn fetch döngüsü)
- Memurai (Redis 6379)

Vite dev server `5173`'te ayağa kalkar; `/api` istekleri 8010'a, `/ws` bağlantıları 8011'e proxy'lenir (`vite.config.ts`).

## Beklenen davranış

Tarayıcı: `http://localhost:5173`

- MapLibre 3D haritası, İstanbul (lon 29.00, lat 41.04), zoom 12, pitch 45°, bearing -20°.
- 3D binalar (`fill-extrusion`, OpenMapTiles `building` source-layer) zoom ≥14'te yükselir.
- Mapterhorn DEM terrain (`terrarium` encoding, exaggeration 1.0); Boğaz tepeleri belirgin.
- Açılışta sürekli görünür modların hatları polyline olarak çizili (21 hat): metro lacivert, Marmaray mor (subway içinden `short_name.startsWith('Marmaray')` ile ayrılıyor), tramvay yeşil, füniküler turuncu. Vapur/otobüs/metrobüs **yok** — KM6 panelinden opt-in olacak.
- ~6911 nokta (canlı araçlar): mavi = mapped (route_id var), kırmızı = unmapped. Z-order: terrain < buildings < route-lines < fleet-circles, yani noktalar polyline'ların ve binaların üstünde.
- Mavi (mapped) noktalar metrobüs koridorunda akıyor — koridorun altında çizgi yok (İETT GTFS shape'siz, Ek A.10; metrobüs polyline'ı Faz 5 OSM snapping ile gelecek).
- Sol üstte "Son güncelleme: X sn önce" göstergesi (yeşil <90s, sarı 90-180s, kırmızı >180s).
- Sağ üstte `NavigationControl` (pitch görselleştirme + zoom).
- 60sn'de bir yeni snapshot gelir; noktalar t0→t1 lineer LERP ile akıcı geçer (KM1 v1).
- DevTools Console:
  - `[map] loaded`
  - `[routes] discovering active routes for 3 modes...`
  - `[routes] found 21 routes, loading shapes...`
  - `[routes] M2 (YENİKAPI - HACIOSMAN) loaded` (×21)
  - `[routes] all done: 21 loaded, 0 skipped`
  - `[ws] connecting → ws://localhost:5173/ws/vehicles/`
  - `[ws] connected`
  - `[ws] snapshot: 6911 vehicles, ~2178 mapped, 6911 in payload`
- DevTools Network → WS sekmesi: `ws://localhost:5173/ws/vehicles/` üzerinden `101 Switching Protocols`.

### Etkileşim

- Sağ tık + sürükle → kamera pitch/bearing değişir.
- Scroll → zoom (9-18 arası).
- NavigationControl pusulasına tıkla → bearing 0°'ye sıfırlanır.

## Reconnect / fallback

- Daphne kapanırsa: WS otomatik reconnect dener (1s → 30s exponential backoff, başarılı handshake'de reset).
- WS 5sn içinde açılmazsa: REST polling (`/api/vehicles/live/`, 60sn) devreye girer.
- WS sonradan bağlanırsa: polling durur, akış WS'e döner.

## Henüz yok (sonraki KM'ler)

- Polyline-aware interpolator v2 (KM4)
- Hat tıklama / focus mode (KM6)
- Otobüs hat seçimi paneli — opt-in (KM6)
- Vapur hatları — KM6 panelinde toggle, açılış varsayılanı kapalı
- Metrobüs polyline'ı (Faz 5 OSM route snapping)
- deck.gl ScatterplotLayer'a geçiş (gerekirse)
