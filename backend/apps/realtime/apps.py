"""Realtime app config with a mapping-cache warm-up hook.

The Redis mapping cache (``iett:mapping:current``) is normally refreshed
by the daily Celery-beat task at UTC 04:00. After a fresh deployment,
dev restart, or Redis flush it can sit empty until that next firing —
during which the is_metrobus categorization lookup falls through to
False for every vehicle. To avoid that gap, ready() does a synchronous
in-process refresh when it detects the cache is empty. Idempotent (no-op
if the cache is already populated) and exceptions are swallowed so a
broken refresh never blocks startup; the system degrades gracefully
while still starting.
"""
from __future__ import annotations

import logging
import os

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class RealtimeConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.realtime"
    verbose_name = "Realtime"

    def ready(self) -> None:
        # Skip under pytest — fakeredis is in use and adapter mocks may
        # not be wired yet at app-ready time.
        import sys
        if any("pytest" in arg for arg in sys.argv):
            return
        # Django's autoreload runs ready() in both the watcher parent
        # and the worker child; only the child (or production, where
        # RUN_MAIN is unset) should warm the cache.
        if os.environ.get("RUN_MAIN") == "false":
            return
        try:
            self._warm_mapping_cache()
        except Exception as exc:  # noqa: BLE001 — startup must not fail
            logger.warning("mapping cache warm-up skipped: %s: %s",
                           type(exc).__name__, exc)

    def _warm_mapping_cache(self) -> None:
        from django.conf import settings
        import redis

        client = redis.from_url(settings.REDIS_URL)
        if client.strlen("iett:mapping:current") > 0:
            return  # already populated

        # Lazy import — eager import here risks a circular load chain
        # through the Celery + tasks tree.
        from apps.realtime.tasks import refresh_iett_mapping

        result = refresh_iett_mapping.apply()
        logger.info("mapping cache warm-up: %s", result.result)
