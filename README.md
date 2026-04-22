# Mini Istanbul 3D

İstanbul'un toplu taşıma ağının gerçek zamanlı 3D dijital haritası. [Mini Tokyo 3D](https://github.com/nagix/mini-tokyo-3d) ilhamlı.

**Durum:** Faz 1 — Veri altyapısı. Geliştirme aktif.

Tek referans doküman: [`MINI_ISTANBUL_3D_SPEC.md`](./MINI_ISTANBUL_3D_SPEC.md) (v0.3).

## Hızlı Başlangıç (geliştirme)

Ön koşul: PostgreSQL 15+ with PostGIS 3, Python 3.11+, Node 20+ (frontend için, Faz 4'te).

```bash
cd backend
python -m venv venv
./venv/Scripts/activate       # Windows
pip install -r requirements/dev.txt
cp .env.example .env          # SECRET_KEY üret, DATABASE_URL doğrula
python manage.py migrate
python manage.py createsuperuser
python manage.py download_gtfs    # İBB'den ZIP'leri çek (Adım 6'dan sonra)
python manage.py import_gtfs      # DB'ye aktar
python manage.py runserver
```

## Proje yapısı

```
backend/           Django + DRF API
  config/          settings (base/dev/prod)
  apps/
    core/          ortak yardımcılar, constants
    gtfs/          statik GTFS modelleri ve komutları
data/raw/          GTFS ZIP indirme yeri (git ignored)
frontend/          MapLibre + Three.js (Faz 4)
```

## Faz durumu

- [ ] Faz 1 — Veri altyapısı (aktif)
- [ ] Faz 2 — Canlı veri adaptörü (İETT SOAP)
- [ ] Faz 3 — WebSocket katmanı
- [ ] Faz 4 — 3D frontend
- [ ] Faz 5 — Metro/Marmaray/Vapur simülasyonu
- [ ] Faz 6 — Cilalama

## Lisans

MIT. Veri: © İstanbul Büyükşehir Belediyesi, © OpenStreetMap katkıda bulunanlar.
