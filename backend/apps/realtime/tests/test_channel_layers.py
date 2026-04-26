"""Smoke tests for Channels infrastructure settings (spec §6.4, ROADMAP 6b-iii).

Read-only assertions over settings — locks in CHANNEL_LAYERS shape,
Channels Redis db=1 (ayrı Celery'den), ASGI_APPLICATION path, ve
INSTALLED_APPS daphne pozisyonu (Channels 4 ASGI runserver override
için en başa olmak zorunda)."""
from __future__ import annotations

from django.conf import settings


def test_channel_layers_uses_redis_backend():
    layer = settings.CHANNEL_LAYERS["default"]
    assert layer["BACKEND"] == "channels_redis.core.RedisChannelLayer"


def test_channels_redis_url_uses_db_1():
    # Memurai db=1 (Celery REDIS_URL db=0'la ayrı). FLUSHDB yanlış
    # db'ye gitme riskine karşı regression guard.
    hosts = settings.CHANNEL_LAYERS["default"]["CONFIG"]["hosts"]
    assert len(hosts) == 1
    assert hosts[0].endswith("/1")


def test_asgi_application_points_at_config_asgi():
    assert settings.ASGI_APPLICATION == "config.asgi.application"


def test_daphne_is_first_installed_app():
    # Channels 4 best practice: daphne, "django.contrib.admin"'den önce
    # yer almalı ki runserver komutu Daphne ASGI versiyonuyla override
    # edilebilsin.
    assert settings.INSTALLED_APPS[0] == "daphne"
