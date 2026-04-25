"""Smoke tests for Celery beat schedule entries (spec §5.7, ROADMAP 5e).

Read-only assertions over ``settings.CELERY_BEAT_SCHEDULE``. We do NOT
spin up a Celery worker / beat process here — the goal is to lock in
the schedule shape (entry names, task paths, intervals, timezone) so
nobody silently re-empties the dict or shifts the cron hour without
also touching this file.
"""
from __future__ import annotations

from celery.schedules import crontab
from django.conf import settings


def test_beat_schedule_has_two_entries():
    schedule = settings.CELERY_BEAT_SCHEDULE
    assert set(schedule.keys()) == {
        "fetch-iett-positions",
        "refresh-iett-mapping",
    }


def test_fetch_task_runs_every_60_seconds():
    entry = settings.CELERY_BEAT_SCHEDULE["fetch-iett-positions"]
    assert entry["task"] == "apps.realtime.tasks.fetch_iett_positions"
    assert entry["schedule"] == 60.0


def test_refresh_task_runs_daily_at_utc_04():
    entry = settings.CELERY_BEAT_SCHEDULE["refresh-iett-mapping"]
    assert entry["task"] == "apps.realtime.tasks.refresh_iett_mapping"
    schedule = entry["schedule"]
    assert isinstance(schedule, crontab)
    assert schedule.hour == {4}
    assert schedule.minute == {0}


def test_celery_timezone_is_utc():
    # Schedule yorumu UTC bağımlı; bu setting değişirse beat
    # zamanlaması kayar. Regression guard.
    assert settings.CELERY_TIMEZONE == "UTC"
