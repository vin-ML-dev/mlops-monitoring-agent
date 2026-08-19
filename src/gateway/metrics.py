"""Prometheus metrics. The gateway<->model boundary is instrumented SEPARATELY
from the public HTTP boundary, so Day 6 can distinguish client errors, gateway
overload, cache behavior, and true backend failures. Keep label cardinality low;
never put secrets/prompts in labels.
"""

from __future__ import annotations

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

# public HTTP boundary
http_requests = Counter(
    "gateway_http_requests_total", "Public HTTP requests", ["method", "route", "status"]
)
http_duration = Histogram(
    "gateway_http_request_duration_seconds", "Public HTTP request duration", ["route"]
)
inflight = Gauge("gateway_inflight_requests", "In-flight public requests")

# gateway <-> model boundary
backend_requests = Counter("gateway_backend_requests_total", "Calls to the model", ["outcome"])
backend_duration = Histogram("gateway_backend_request_duration_seconds", "Model call duration")
backend_inflight = Gauge("gateway_backend_inflight", "In-flight model calls")

# policy signals
cache_events = Counter("gateway_cache_requests_total", "Cache lookups", ["result"])
rate_limit_rejections = Counter("gateway_rate_limit_rejections_total", "Rate-limit rejections")
backpressure_rejections = Counter("gateway_backpressure_rejections_total", "Backpressure 503s")
breaker_state = Gauge("gateway_circuit_breaker_state", "0=closed 1=half_open 2=open")
breaker_transitions = Counter(
    "gateway_circuit_breaker_transitions_total", "Breaker transitions", ["to_state"]
)

_STATE_VALUE = {"closed": 0, "half_open": 1, "open": 2}


def set_breaker_state(state: str) -> None:
    breaker_state.set(_STATE_VALUE.get(state, 0))


def render() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
