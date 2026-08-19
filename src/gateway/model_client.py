"""Pooled async HTTP client to the model, with a timeout budget and a conservative
retry. One client per process (created at startup), never one per request.

Retry only narrow transient PRE-response failures (connect errors, backend
502/503/504), at most one retry, and NEVER after streaming has started.
"""

from __future__ import annotations

import asyncio
import random

from .errors import BackendTimeout, BackendUnavailable

_RETRYABLE_STATUS = {502, 503, 504}


def is_retryable_status(status: int) -> bool:
    return status in _RETRYABLE_STATUS


def is_retryable_exception(exc: Exception) -> bool:
    import httpx

    return isinstance(
        exc,
        httpx.ConnectError | httpx.ConnectTimeout | httpx.ReadError | httpx.RemoteProtocolError,
    )


def backoff_seconds(cfg: dict) -> float:
    lo = cfg["retry"]["backoff_ms_min"]
    hi = cfg["retry"]["backoff_ms_max"]
    return random.uniform(lo, hi) / 1000.0


class ModelClient:
    """Wraps a shared httpx.AsyncClient. Build with `create` in the app lifespan."""

    def __init__(self, client, cfg: dict):
        self._client = client
        self._cfg = cfg
        self._url = cfg["model"]["base_url"].rstrip("/") + cfg["model"]["chat_path"]

    @classmethod
    def create(cls, cfg: dict):
        import httpx

        t = cfg["timeouts"]
        timeout = httpx.Timeout(
            connect=t["connect"], read=t["read"], write=t["write"], pool=t["pool"]
        )
        limits = httpx.Limits(max_connections=100, max_keepalive_connections=20)
        client = httpx.AsyncClient(timeout=timeout, limits=limits)
        return cls(client, cfg)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def complete(self, payload: dict) -> dict:
        """Non-streaming call with at most one retry on a transient pre-response error."""
        import httpx

        attempts = self._cfg["retry"]["max_attempts"]
        last_exc: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                resp = await self._client.post(self._url, json=payload)
                if is_retryable_status(resp.status_code) and attempt < attempts:
                    await asyncio.sleep(backoff_seconds(self._cfg))
                    continue
                if resp.status_code >= 500:
                    raise BackendUnavailable()
                resp.raise_for_status()
                return resp.json()
            except httpx.TimeoutException as exc:
                raise BackendTimeout() from exc
            except Exception as exc:
                last_exc = exc
                if is_retryable_exception(exc) and attempt < attempts:
                    await asyncio.sleep(backoff_seconds(self._cfg))
                    continue
                raise BackendUnavailable() from exc
        raise BackendUnavailable() from last_exc
