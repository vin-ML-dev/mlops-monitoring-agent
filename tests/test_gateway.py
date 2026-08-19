"""Tests for the Day 5 gateway logic that don't need Redis/httpx/a cluster:
the circuit breaker state machine, auth, cache keys, rate-limit math, the error
taxonomy, validation, and bounded concurrency.

The breaker and concurrency tests are the important ones — they prove the
overload/failure behavior the gateway promises.
"""

from __future__ import annotations

import asyncio

import pytest

from src.gateway import load_gateway_cfg
from src.gateway.auth import extract_bearer, verify_api_key
from src.gateway.cache import build_cache_key, is_cacheable
from src.gateway.circuit_breaker import CircuitBreaker, State
from src.gateway.concurrency import BoundedConcurrency
from src.gateway.errors import Overloaded, RateLimited, ValidationFailed
from src.gateway.model_client import is_retryable_status
from src.gateway.rate_limit import fingerprint, window_key
from src.gateway.request_id import get_or_create_request_id
from src.gateway.schemas import GenerateRequest, enforce_limits

CFG = load_gateway_cfg()


# ---------------- circuit breaker ----------------
def test_breaker_opens_after_threshold():
    cb = CircuitBreaker(failure_threshold=3, open_seconds=10)
    for _ in range(3):
        cb.record_failure()
    assert cb.state == State.OPEN
    assert cb.allow() is False


def test_breaker_half_opens_after_cooldown_then_closes_on_success():
    clock = {"t": 0.0}
    cb = CircuitBreaker(3, open_seconds=10, half_open_probes=1, now=lambda: clock["t"])
    for _ in range(3):
        cb.record_failure()
    assert cb.state == State.OPEN
    clock["t"] = 11  # cooldown elapsed
    assert cb.state == State.HALF_OPEN
    assert cb.allow() is True  # one probe allowed
    assert cb.allow() is False  # no more probes
    cb.record_success()  # probe succeeded
    assert cb.state == State.CLOSED


def test_breaker_reopens_if_probe_fails():
    clock = {"t": 0.0}
    cb = CircuitBreaker(2, open_seconds=5, now=lambda: clock["t"])
    cb.record_failure()
    cb.record_failure()
    clock["t"] = 6
    assert cb.state == State.HALF_OPEN
    cb.allow()
    cb.record_failure()  # probe failed
    assert cb.state == State.OPEN


def test_breaker_success_resets_failure_count():
    cb = CircuitBreaker(3, open_seconds=10)
    cb.record_failure()
    cb.record_failure()
    cb.record_success()  # resets
    cb.record_failure()
    cb.record_failure()
    assert cb.state == State.CLOSED  # only 2 in a row, never hit 3


# ---------------- auth ----------------
def test_extract_bearer():
    assert extract_bearer("Bearer abc123") == "abc123"
    assert extract_bearer("abc123") == "abc123"
    assert extract_bearer(None) is None


def test_verify_api_key():
    assert verify_api_key("Bearer secret", "secret") is True
    assert verify_api_key("Bearer wrong", "secret") is False
    assert verify_api_key(None, "secret") is False
    assert verify_api_key("Bearer secret", "") is False


# ---------------- cache key ----------------
def test_cache_key_is_deterministic_and_versioned():
    p = {"messages": [{"role": "user", "content": "hi"}], "temperature": 0}
    k1 = build_cache_key(p, "v1", "finbot-1.0.0")
    k2 = build_cache_key(dict(reversed(list(p.items()))), "v1", "finbot-1.0.0")
    assert k1 == k2  # canonical -> order-independent
    assert k1.startswith("gateway:v1:model:finbot-1.0.0:")


def test_cache_key_changes_with_model_version():
    p = {"messages": [{"role": "user", "content": "hi"}]}
    assert build_cache_key(p, "v1", "finbot-1.0.0") != build_cache_key(p, "v1", "finbot-1.1.0")


def test_is_cacheable_only_deterministic_nonstream():
    assert is_cacheable(0, False) is True
    assert is_cacheable(0.7, False) is False
    assert is_cacheable(0, True) is False


# ---------------- rate-limit math ----------------
def test_fingerprint_hides_raw_key():
    fp = fingerprint("super-secret-key")
    assert "secret" not in fp and len(fp) == 16


def test_window_key_rolls_with_time():
    fp = fingerprint("k")
    assert window_key(fp, 60, 0) != window_key(fp, 60, 60)
    assert window_key(fp, 60, 10) == window_key(fp, 60, 59)  # same 60s window


# ---------------- error taxonomy ----------------
def test_error_codes_and_status():
    assert RateLimited(retry_after=5).status == 429
    assert RateLimited(retry_after=5).retry_after == 5
    assert Overloaded().status == 503


def test_retryable_status():
    assert is_retryable_status(503) is True
    assert is_retryable_status(500) is False
    assert is_retryable_status(200) is False


# ---------------- request id ----------------
def test_request_id_accepts_safe_and_generates_otherwise():
    assert get_or_create_request_id("abc-123_x") == "abc-123_x"
    generated = get_or_create_request_id("bad id with spaces!")
    assert len(generated) == 32  # uuid4 hex
    assert get_or_create_request_id(None)  # non-empty


# ---------------- validation ----------------
def test_validation_rejects_too_many_messages():
    req = GenerateRequest(messages=[{"role": "user", "content": "x"}] * 40)
    with pytest.raises(ValidationFailed):
        enforce_limits(req, CFG)


def test_validation_rejects_max_tokens_over_cap():
    req = GenerateRequest(messages=[{"role": "user", "content": "x"}], max_tokens=99999)
    with pytest.raises(ValidationFailed):
        enforce_limits(req, CFG)


def test_schema_bounds_temperature():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        GenerateRequest(messages=[{"role": "user", "content": "x"}], temperature=9)


# ---------------- bounded concurrency (backpressure) ----------------
def test_bounded_concurrency_rejects_when_full():
    async def run():
        bc = BoundedConcurrency(limit=1, wait_timeout=0.05)
        async with bc:  # take the only permit
            with pytest.raises(Overloaded):  # second acquire times out -> 503
                async with bc:
                    pass

    asyncio.run(run())
