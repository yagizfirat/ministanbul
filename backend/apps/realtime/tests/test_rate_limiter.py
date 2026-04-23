from datetime import timedelta

import fakeredis
import pytest
from freezegun import freeze_time

from apps.realtime.rate_limit import LimitStatus, SlidingWindowLimiter


@pytest.fixture
def redis_client():
    return fakeredis.FakeStrictRedis()


@pytest.fixture
def limiter(redis_client):
    return SlidingWindowLimiter(
        redis_client=redis_client,
        name="test:rl",
        window_seconds=2400,
        soft_limit=60,
        hard_limit=72,
        cooldown_seconds=1800,
    )


def test_empty_window_returns_ok(limiter):
    assert limiter.check() == LimitStatus.OK
    assert limiter.current_count() == 0


def test_record_call_increments_count(limiter):
    limiter.record_call()
    limiter.record_call()
    assert limiter.current_count() == 2


def test_soft_limit_returns_warning(limiter):
    with freeze_time("2026-04-23 12:00:00"):
        for _ in range(60):
            limiter.record_call()
        assert limiter.current_count() == 60
        assert limiter.check() == LimitStatus.WARNING


def test_hard_limit_returns_blocked(limiter):
    with freeze_time("2026-04-23 12:00:00"):
        for _ in range(72):
            limiter.record_call()
        assert limiter.current_count() == 72
        assert limiter.check() == LimitStatus.BLOCKED


def test_window_slides_old_calls_evicted(limiter):
    with freeze_time("2026-04-23 12:00:00") as frozen:
        for _ in range(30):
            limiter.record_call()
        assert limiter.current_count() == 30
        frozen.tick(delta=timedelta(minutes=41))
        assert limiter.current_count() == 0


def test_partial_window_slide(limiter):
    with freeze_time("2026-04-23 12:00:00") as frozen:
        for _ in range(40):
            limiter.record_call()
        frozen.tick(delta=timedelta(minutes=20))
        assert limiter.current_count() == 40


def test_record_violation_enters_cooldown(limiter):
    limiter.record_violation()
    assert limiter.in_cooldown() is True
    assert limiter.check() == LimitStatus.COOLDOWN


def test_cooldown_expires(limiter):
    with freeze_time("2026-04-23 12:00:00") as frozen:
        limiter.record_violation()
        assert limiter.check() == LimitStatus.COOLDOWN
        frozen.tick(delta=timedelta(minutes=31))
        assert limiter.in_cooldown() is False
        assert limiter.check() == LimitStatus.OK


def test_status_snapshot_fields(limiter):
    limiter.record_call()
    snap = limiter.status_snapshot()
    expected = {
        "status",
        "count",
        "soft",
        "hard",
        "remaining",
        "window_seconds",
        "cooldown_active",
        "cooldown_expires_at",
    }
    assert expected.issubset(snap.keys())
    assert snap["count"] == 1
    assert snap["soft"] == 60
    assert snap["hard"] == 72
    assert snap["window_seconds"] == 2400
    assert snap["cooldown_active"] is False
    assert snap["cooldown_expires_at"] is None


def test_remaining_calculation(limiter):
    with freeze_time("2026-04-23 12:00:00"):
        for _ in range(30):
            limiter.record_call()
        assert limiter.remaining() == 42
