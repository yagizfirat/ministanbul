"""Redis distributed lock — Phase 2 Step 4b.

Context manager that wraps a critical section in a ``SETNX + EX`` lock so
that multiple Celery workers don't hit the same upstream concurrently.
Only one worker holds the lock at a time; others get ``LockAcquisitionError``
and must decide whether to skip or retry.

Release is atomic via a Lua script — a naive GET-then-DEL would race
with a concurrent worker that re-acquired the lock after our TTL
expired, and our DEL would strip *their* lock. The Lua path checks that
the stored token matches ours before deleting, so we never release
someone else's lock.

``timeout_seconds`` is the upper bound on the critical section. If the
caller hangs, Redis expires the key and the next worker can proceed.
This is a serialization guarantee ("one at a time, more or less"),
not strict at-most-once — if the work exceeds ``timeout_seconds``,
two workers may briefly overlap.
"""
from __future__ import annotations

import logging
import uuid
from contextlib import contextmanager
from typing import Iterator

logger = logging.getLogger(__name__)


_RELEASE_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
else
    return 0
end
"""


class DistributedLockError(Exception):
    pass


class LockAcquisitionError(DistributedLockError):
    pass


class LockReleaseError(DistributedLockError):
    pass


@contextmanager
def distributed_lock(
    redis_client,
    key: str,
    timeout_seconds: int = 30,
) -> Iterator[str]:
    """Acquire ``lock:{key}`` for the duration of the block.

    Yields the per-acquire token (usually discarded; useful for tests
    and for caller logging). Raises :class:`LockAcquisitionError` if the
    lock is currently held. On exit, quietly continues if the lock was
    already gone (expired or stolen) — the critical section already ran.
    """
    lock_key = f"lock:{key}"
    token = uuid.uuid4().hex

    acquired = redis_client.set(lock_key, token, nx=True, ex=timeout_seconds)
    if not acquired:
        raise LockAcquisitionError(f"lock {lock_key!r} held by another worker")

    try:
        yield token
    finally:
        released = redis_client.eval(_RELEASE_LUA, 1, lock_key, token)
        if not int(released):
            logger.warning(
                "lock %s was not held by this worker on release "
                "(expired or stolen); continuing",
                lock_key,
            )
