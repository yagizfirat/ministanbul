from datetime import timedelta
from unittest.mock import patch

import fakeredis
import pytest
from freezegun import freeze_time

from apps.realtime.locks import LockAcquisitionError, distributed_lock


@pytest.fixture
def redis_client():
    return fakeredis.FakeStrictRedis()


def test_acquire_release_happy_path(redis_client):
    with distributed_lock(redis_client, "job1", timeout_seconds=30):
        assert redis_client.exists("lock:job1") == 1
    assert redis_client.exists("lock:job1") == 0


def test_second_acquire_raises(redis_client):
    with distributed_lock(redis_client, "job1", timeout_seconds=30):
        with pytest.raises(LockAcquisitionError):
            with distributed_lock(redis_client, "job1", timeout_seconds=30):
                pass


def test_expire_releases_lock(redis_client):
    with freeze_time("2026-04-23 12:00:00") as frozen:
        # Simulate a worker that crashed mid-critical-section: raw SET with TTL,
        # no release.
        redis_client.set("lock:job1", "crashed-worker-token", nx=True, ex=30)
        assert redis_client.exists("lock:job1") == 1

        frozen.tick(delta=timedelta(seconds=31))
        # TTL expired → next worker can acquire cleanly.
        with distributed_lock(redis_client, "job1", timeout_seconds=30):
            assert redis_client.exists("lock:job1") == 1


def test_release_only_own_lock(redis_client, caplog):
    with caplog.at_level("WARNING", logger="apps.realtime.locks"):
        with distributed_lock(redis_client, "job1", timeout_seconds=30):
            # Someone else overwrote our lock mid-flight (shouldn't happen in
            # practice, but defensively: our release must not strip their key).
            redis_client.set("lock:job1", "thief-token")

    assert redis_client.get("lock:job1") == b"thief-token"
    assert any(
        "not held by this worker" in record.getMessage()
        for record in caplog.records
    )


def test_lua_release_atomic(redis_client):
    with patch.object(redis_client, "eval", wraps=redis_client.eval) as mock_eval:
        with distributed_lock(redis_client, "job1", timeout_seconds=30):
            pass

    assert mock_eval.called, "release path must go through redis.eval (Lua)"
    script = mock_eval.call_args.args[0]
    assert "redis.call('GET'" in script
    assert "redis.call('DEL'" in script


def test_nested_different_keys(redis_client):
    with distributed_lock(redis_client, "job1", timeout_seconds=30):
        with distributed_lock(redis_client, "job2", timeout_seconds=30):
            assert redis_client.exists("lock:job1") == 1
            assert redis_client.exists("lock:job2") == 1

    assert redis_client.exists("lock:job1") == 0
    assert redis_client.exists("lock:job2") == 0
