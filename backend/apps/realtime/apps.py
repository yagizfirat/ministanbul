"""Realtime app config + KM5-f mapping cache warm-up startup hook.

Mapping cache (``iett:mapping:current``) Celery beat task ``refresh-
iett-mapping`` tarafından her gün UTC 04:00'te yenileniyor. Fresh
deployment / dev restart / Redis flush sonrası ilk doğal tetiklemeye
kadar 24 saate kadar boş kalabilir; KM5-e.1'den itibaren is_metrobus
categorize lookup'ı bu cache'e bağlı (KM5-a flag'tan bağımsız), boş
cache → tüm vehicle'lar is_metrobus=False (kategorize sinyali kayıp).

Fix: Django ready() içinde cache boşsa sync refresh tetiklenir
(Celery worker'a değil, in-process). Idempotent — cache canlıysa
no-op. Her exception yutulur — startup patlamamalı, mapping yokken
sistem degradeli ama çalışır halde başlar.
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
        # Test koşumunda warm-up atlansın: pytest fakeredis kullanıyor,
        # ready() seam'de gerçek Redis'e dokunmak gereksiz + adapter
        # mock'ları daha bağlanmadan çağrılır. Yardımcı sentinel:
        # pytest runner sys.argv[0] "pytest" içerir.
        import sys
        if any("pytest" in arg for arg in sys.argv):
            return
        # autoreload child process koruması: runserver/daphne autoreload
        # ana proseste de child proseste de ready() çağırır. Yalnız child
        # (RUN_MAIN=true) ya da prod (RUN_MAIN unset) çağrı yeterli, ana
        # autoreload watcher'da skip et.
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
            return  # canlı cache, no-op

        # Lazy import — ready() çağrı zinciri Celery + tasks ağacını
        # baştan yüklerse circular import potansiyeli var.
        from apps.realtime.tasks import refresh_iett_mapping

        result = refresh_iett_mapping.apply()
        logger.info("mapping cache warm-up: %s", result.result)
