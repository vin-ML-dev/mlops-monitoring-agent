"""Response cache: versioned canonical keys, deterministic-only, fail-open.

Key includes everything that changes the answer (model version, schema version,
full messages, decoding params). Invalidation is by VERSION prefix, not FLUSHDB.
On any Redis error we bypass the cache (fail open) — a cache outage must not stop
inference.
"""

from __future__ import annotations

import hashlib
import json


def build_cache_key(payload: dict, schema_version: str, model_version: str) -> str:
    """SHA-256 over canonical JSON, prefixed with schema + model version."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"gateway:{schema_version}:model:{model_version}:{digest}"


def is_cacheable(temperature: float, stream: bool) -> bool:
    """Cache only deterministic, non-streaming responses."""
    return temperature == 0 and not stream


class ResponseCache:
    def __init__(self, redis, ttl_seconds: int):
        self._r = redis
        self.ttl = ttl_seconds

    async def get(self, key: str):
        try:
            raw = await self._r.get(key)
            return json.loads(raw) if raw else None
        except Exception:  # noqa: BLE001 - fail open: a cache error must not break serving
            return None

    async def set(self, key: str, value: dict) -> None:
        import contextlib

        with contextlib.suppress(Exception):  # fail open: a cache error must not break serving
            await self._r.set(key, json.dumps(value), ex=self.ttl)
