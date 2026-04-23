"""Celery app factory.

Configures the Celery instance used by the project. Task discovery is driven by
INSTALLED_APPS — each app may expose a `tasks.py` module. Config keys with the
`CELERY_` prefix in Django settings are loaded here (namespace="CELERY").
"""
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

app = Celery("config")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
