"""Pydantic schemas for the realtime pipeline.

Populated in Phase 2 Step 2: canonical VehiclePosition model (see spec §5.3)
that every adapter yields, independent of upstream field names. This schema
is the contract between adapters and the WebSocket / REST layers.

TODO (Phase 2 Step 2): VehiclePosition (KapiNo, lat/lon, hiz, saat, hat_kodu,
guzergah_kodu, source, fetched_at).
"""
