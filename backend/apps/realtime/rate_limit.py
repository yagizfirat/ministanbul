"""Redis ZSET sliding window rate limiter — Phase 2 Step 4a.

Enforces the observed IETT SOAP envelope: ~40-minute sliding window,
soft limit 60 (our target cadence), hard limit 72 (empirical ceiling
before the gateway starts returning Policy Falsified). A violation —
e.g. an HTTP 500 with "Policy Falsified" — triggers a cooldown during
which fetch() should not be attempted (default 30 min).

Redis keys per limiter instance (one per upstream, e.g.
`iett:ratelimit:fleet`):

  ZSET  {name}            — call timestamps; score = time.time(),
                             member = "{score}:{uuid4}" so freezegun and
                             extremely-fast fires don't collide on rewrite
  STR   {name}:cooldown   — absolute until-timestamp as ascii float,
                             EX {cooldown_seconds} so real Redis prunes it

Cooldown uses BOTH the TTL and the stored until-value: the TTL lets real
Redis clean up; the until-value lets the limiter stay correct under frozen
clocks where TTL doesn't tick. Either path is authoritative on its own.

Thread-safe — all state lives in Redis, no process-local caches.
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from enum import Enum


class LimitStatus(Enum):
    OK = "OK"
    WARNING = "WARNING"
    BLOCKED = "BLOCKED"
    COOLDOWN = "COOLDOWN"


class SlidingWindowLimiter:
    def __init__(
        self,
        redis_client,
        name: str,
        window_seconds: int,
        soft_limit: int,
        hard_limit: int,
        cooldown_seconds: int,
    ) -> None:
        self.redis = redis_client
        self.name = name
        self.window_seconds = window_seconds
        self.soft_limit = soft_limit
        self.hard_limit = hard_limit
        self.cooldown_seconds = cooldown_seconds

    @property
    def _cooldown_key(self) -> str:
        return f"{self.name}:cooldown"

    def _now(self) -> float:
        return time.time()

    def _evict_expired(self, now: float) -> None:
        threshold = now - self.window_seconds
        self.redis.zremrangebyscore(self.name, 0, threshold)

    def record_call(self) -> None:
        now = self._now()
        member = f"{now}:{uuid.uuid4()}"
        self.redis.zadd(self.name, {member: now})
        self._evict_expired(now)

    def record_violation(self) -> None:
        now = self._now()
        until = now + self.cooldown_seconds
        self.redis.set(self._cooldown_key, str(until), ex=self.cooldown_seconds)

    def _cooldown_until(self) -> float | None:
        val = self.redis.get(self._cooldown_key)
        if val is None:
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            # Value corrupted — treat as active until the TTL clears it.
            return self._now() + self.cooldown_seconds

    def in_cooldown(self) -> bool:
        until = self._cooldown_until()
        return until is not None and self._now() < until

    def current_count(self) -> int:
        now = self._now()
        self._evict_expired(now)
        return int(self.redis.zcard(self.name))

    def remaining(self) -> int:
        return max(0, self.hard_limit - self.current_count())

    def check(self) -> LimitStatus:
        if self.in_cooldown():
            return LimitStatus.COOLDOWN
        count = self.current_count()
        if count >= self.hard_limit:
            return LimitStatus.BLOCKED
        if count >= self.soft_limit:
            return LimitStatus.WARNING
        return LimitStatus.OK

    def status_snapshot(self) -> dict:
        now = self._now()
        self._evict_expired(now)
        count = int(self.redis.zcard(self.name))

        until = self._cooldown_until()
        cooldown_active = until is not None and now < until
        cooldown_expires_at = (
            datetime.fromtimestamp(until, tz=timezone.utc) if cooldown_active else None
        )

        if cooldown_active:
            status = LimitStatus.COOLDOWN
        elif count >= self.hard_limit:
            status = LimitStatus.BLOCKED
        elif count >= self.soft_limit:
            status = LimitStatus.WARNING
        else:
            status = LimitStatus.OK

        return {
            "status": status.value,
            "count": count,
            "soft": self.soft_limit,
            "hard": self.hard_limit,
            "remaining": max(0, self.hard_limit - count),
            "window_seconds": self.window_seconds,
            "cooldown_active": cooldown_active,
            "cooldown_expires_at": cooldown_expires_at,
        }
