"""Celery tasks for the realtime pipeline.

Populated in Phase 2 Step 5: periodic `fetch_iett_positions` (60s cadence,
spec §4.2.1) and a daily `refresh_iett_mapping` (yesterday's ArsivGorev,
spec Ek A.13). Beat schedule is wired in base settings.

TODO (Phase 2 Step 5): @shared_task fetch_iett_positions, refresh_iett_mapping.
"""
