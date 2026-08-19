"""Distributed fixed-window rate limiter (Redis), shared across gateway replicas.

Keys use a fingerprint of the API key (never the raw key). Redis failure is
handled by the caller as a security-first 503 (don't silently drop enforcement).
429 (caller over quota) is distinct from 503 (service can't accept work).
"""

from __future__ import annotations

import hashlib


def fingerprint(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:16]


def window_key(fp: str, window_seconds: int, now_epoch: float) -> str:
    window = int(now_epoch // window_seconds)
    return f"rate:{fp}:{window}"


class RateLimiter:
    def __init__(self, redis, limit: int, window_seconds: int):
        self._r = redis
        self.limit = limit
        self.window = window_seconds

    async def check(self, api_key: str, now_epoch: float) -> tuple[bool, int]:
        """Return (allowed, retry_after_seconds). Raises on Redis error (caller -> 503)."""
        key = window_key(fingerprint(api_key), self.window, now_epoch)
        count = await self._r.incr(key)
        if count == 1:
            await self._r.expire(key, self.window)
        if count > self.limit:
            retry_after = self.window - int(now_epoch % self.window)
            return False, max(retry_after, 1)
        return True, 0
