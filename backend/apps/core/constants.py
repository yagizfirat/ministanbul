"""Project-wide constants. No magic numbers elsewhere."""

SRID_WGS84 = 4326
DEFAULT_TIMEZONE = "Europe/Istanbul"

IETT_FETCH_INTERVAL_SECONDS = 60
IETT_RATE_LIMIT_WINDOW_MINUTES = 40
IETT_RATE_LIMIT_MAX_CALLS = 72
IETT_RATE_LIMIT_SOFT_CALLS = 60
IETT_COOLDOWN_MINUTES = 30

STALE_CACHE_TTL_SECONDS = 5 * 60
STALE_CACHE_TTL_ERROR_SECONDS = 45 * 60

# İstanbul metropolitan bounding box — envelope calibrated from observed
# İETT + public stops (2026-04-22). Covers:
#   - S: Gebze İstasyonu (40.78)
#   - N: Yalıköy (Kıyıköy/Kırklareli sınırı, 41.48) — İETT rural bus routes
#   - W: Silivri batısı (27.9992), Binkılıç/Hallaçlı köyleri
#   - E: Şile ÇELEBİKÖY (29.9067)
# Margin ~2 km on each side. Sanitized coords outside this box indicate
# the recovery algorithm misfired — real data stays in.
ISTANBUL_LAT_MIN = 40.7
ISTANBUL_LAT_MAX = 41.5
ISTANBUL_LON_MIN = 27.95
ISTANBUL_LON_MAX = 29.95

# NOTE — Metrobüs whitelist v0.8.0'da settings'e taşındı:
# ``django.conf.settings.METROBUS_SHORT_NAMES``. Eski ``METROBUS_ROUTES``
# adı v0.7.x'te "mapping whitelist exception" semantiğiyle yüklenmişti;
# v0.8.0'da Ek A.18 Rapor 12 sonucunda whitelist exception iptal oldu,
# sabit yalnız frontend kategorize (antrasit gri) için kalır.
