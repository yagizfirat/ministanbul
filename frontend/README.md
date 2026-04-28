# Mini Istanbul 3D — Frontend

Vite + TypeScript + MapLibre GL JS. Faz 4 KM1 iskeleti.

## Geliştirme

```bash
cd frontend
npm install      # ilk sefer
npm run dev      # http://localhost:5173
```

## Backend bağımlılığı

`npm run dev` öncesi şunlar ayakta olmalı:

- Django HTTP — `localhost:8010` (REST: `/api/vehicles/live/`)
- Daphne ASGI — `localhost:8011` (WS: `/ws/vehicles/`)
- Celery worker + beat (60sn fetch döngüsü)
- Memurai (Redis 6379)

Vite dev server `5173`'te ayağa kalkar; `/api` istekleri 8010'a, `/ws` bağlantıları 8011'e proxy'lenir (`vite.config.ts`).

## Beklenen ilk açılış

Tarayıcı: `http://localhost:5173`

- Boş MapLibre haritası, İstanbul merkez (lon 28.98, lat 41.02), zoom 11.
- DevTools Console:
  - `[map] loaded`
  - `[ws] connecting → ws://localhost:5173/ws/vehicles/`
  - `[ws] connected`
  - `[ws] snapshot: <N> vehicles, <M> mapped, <N> in payload` (~60sn'de bir)
- DevTools Network → WS sekmesi: `ws://localhost:5173/ws/vehicles/` üzerinden `101 Switching Protocols`.

Backend kapanırsa client otomatik reconnect dener (1s → 30s exponential backoff, başarılı handshake'de reset).

## Henüz yok

- Araç render (KM1 b/2)
- Lineer interpolator + 60 FPS rAF (KM1 b/2)
- "Son güncelleme: X sn önce" UI (KM1 b/2)
- 3D bina, terrain, deck.gl katmanı (sonraki KM'ler)
