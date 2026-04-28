# Mini Istanbul 3D — Frontend

Vite + TypeScript + MapLibre GL JS. Faz 4 KM1.

## Geliştirme

Backend stack'i tek tıkla:

```
scripts\start_stack.bat        # Django 8010, Daphne 8011, Celery worker + beat (4 PowerShell penceresi)
```

Memurai zaten Windows servisi, ayrı başlatma yok.

Frontend:

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

## Beklenen davranış

Tarayıcı: `http://localhost:5173`

- MapLibre haritası, İstanbul merkez (lon 28.98, lat 41.02), zoom 11.
- ~6911 nokta (canlı araçlar): mavi = mapped (route_id var), kırmızı = unmapped.
- Sağ üstte "Son güncelleme: X sn önce" göstergesi (yeşil <90s, sarı 90-180s, kırmızı >180s).
- 60sn'de bir yeni snapshot gelir; noktalar t0→t1 lineer LERP ile akıcı geçer (KM1 v1).
- DevTools Console:
  - `[map] loaded`
  - `[ws] connecting → ws://localhost:5173/ws/vehicles/`
  - `[ws] connected`
  - `[ws] snapshot: 6911 vehicles, ~2178 mapped, 6911 in payload`
- DevTools Network → WS sekmesi: `ws://localhost:5173/ws/vehicles/` üzerinden `101 Switching Protocols`.

## Reconnect / fallback

- Daphne kapanırsa: WS otomatik reconnect dener (1s → 30s exponential backoff, başarılı handshake'de reset).
- WS 5sn içinde açılmazsa: REST polling (`/api/vehicles/live/`, 60sn) devreye girer.
- WS sonradan bağlanırsa: polling durur, akış WS'e döner.

## Henüz yok (sonraki KM'ler)

- Polyline-temelli interpolator v2 (KM4)
- Hat filtresi UI (Faz 5)
- 3D bina + terrain (KM2)
- deck.gl ScatterplotLayer'a geçiş (gerekirse)
