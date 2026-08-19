"""Bounded backend concurrency (backpressure), per gateway pod.

Acquire a permit before calling the model; if none is free within the wait
timeout, raise Overloaded -> the handler returns 503 + Retry-After. This stops
the gateway from stampeding a CPU model. NOTE: this limit is PER POD — with N
replicas the model can see up to N x max_backend concurrent calls.
"""

from __future__ import annotations

import asyncio

from .errors import Overloaded


class BoundedConcurrency:
    def __init__(self, limit: int, wait_timeout: float):
        self.limit = limit
        self.wait_timeout = wait_timeout
        self._sem = asyncio.Semaphore(limit)

    @property
    def in_use(self) -> int:
        return self.limit - self._sem._value  # type: ignore[attr-defined]

    async def __aenter__(self):
        try:
            await asyncio.wait_for(self._sem.acquire(), timeout=self.wait_timeout)
        except TimeoutError as exc:
            raise Overloaded(retry_after=int(self.wait_timeout) or 1) from exc
        return self

    async def __aexit__(self, *exc) -> None:
        self._sem.release()
