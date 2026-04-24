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

# Metrobüs hatları — 34 ile 34Z arası kapalı whitelist. Regex
# `^34[A-Z]*$` pattern'i `340`, `341` gibi normal İETT otobüslerini ve
# gelecekte eklenebilecek `34D`/`34X` gibi değişiklikleri yanlış
# pozitif/negatif yakalar; sabit liste yılda 1-2 kez elle güncellenen
# bir veri. Spec §3.3 ve Faz 2 Adım 5a discovery query DB'de tam
# match olduğunu doğruladı (10/10, 34-prefix'li başka short_name yok).
METROBUS_ROUTES = frozenset({
    "34", "34A", "34AS", "34B", "34BZ",
    "34C", "34G", "34T", "34U", "34Z",
})
