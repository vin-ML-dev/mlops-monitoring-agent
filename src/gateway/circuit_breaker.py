"""Circuit breaker — closed -> open -> half-open -> closed.

Local to each gateway process (not Redis-backed), so a model outage needs no Redis
to detect and a Redis failure can't disable protection. Pure logic with an
injectable clock, so it's fully testable offline.

Counts BACKEND/system failures (connect errors, backend 5xx, selected timeouts) —
never client 4xx. The breaker answers "is the model dependency unhealthy?", not
"did any request fail?"
"""

from __future__ import annotations

import time
from enum import Enum


class State(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int,
        open_seconds: float,
        half_open_probes: int = 1,
        now=time.monotonic,
    ):
        self.failure_threshold = failure_threshold
        self.open_seconds = open_seconds
        self.half_open_probes = half_open_probes
        self._now = now
        self._state = State.CLOSED
        self._failures = 0
        self._opened_at = 0.0
        self._half_open_calls = 0

    @property
    def state(self) -> State:
        self._maybe_half_open()
        return self._state

    def _maybe_half_open(self) -> None:
        if self._state == State.OPEN and (self._now() - self._opened_at) >= self.open_seconds:
            self._state = State.HALF_OPEN
            self._half_open_calls = 0

    def allow(self) -> bool:
        """Should we attempt a backend call right now?"""
        self._maybe_half_open()
        if self._state == State.CLOSED:
            return True
        if self._state == State.OPEN:
            return False
        # HALF_OPEN: allow a limited number of probe calls
        if self._half_open_calls < self.half_open_probes:
            self._half_open_calls += 1
            return True
        return False

    def record_success(self) -> None:
        if self._state == State.HALF_OPEN:
            self._close()
        else:
            self._failures = 0

    def record_failure(self) -> None:
        if self._state == State.HALF_OPEN:
            self._open()
            return
        self._failures += 1
        if self._failures >= self.failure_threshold:
            self._open()

    def _open(self) -> None:
        self._state = State.OPEN
        self._opened_at = self._now()
        self._failures = 0

    def _close(self) -> None:
        self._state = State.CLOSED
        self._failures = 0
        self._half_open_calls = 0
