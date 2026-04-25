"""Inject the ``Live Vehicles`` dashboard URL into the default admin site.

Django auto-discovers each app's ``admin.py`` exactly once at startup
(via ``AdminConfig.ready`` → ``admin.autodiscover()``), so this monkey
patch happens before the URL resolver builds the admin patterns. We
guard with a sentinel attribute to make repeat imports a no-op (test
runners can import modules more than once).

The view itself lives in :mod:`apps.realtime.admin_views`; we lazy-
import it inside ``_get_urls`` to keep ``admin.py`` cheap and avoid
pulling Redis / adapter imports into the admin discovery path.
"""
from __future__ import annotations

from django.contrib import admin
from django.urls import path

if not getattr(admin.site, "_live_vehicles_patched", False):
    _original_get_urls = admin.site.get_urls

    def _get_urls():
        from apps.realtime.admin_views import live_vehicles_view

        custom = [
            path(
                "live-vehicles/",
                admin.site.admin_view(live_vehicles_view),
                name="live_vehicles",
            ),
        ]
        return custom + _original_get_urls()

    admin.site.get_urls = _get_urls
    admin.site._live_vehicles_patched = True
