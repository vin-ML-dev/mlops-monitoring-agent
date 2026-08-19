"""The FastAPI gateway. Wires the request lifecycle from the Day 5 theory guide:

request id -> auth -> validate -> limits -> rate-limit -> cache lookup ->
bounded concurrency -> circuit breaker -> model call (timeout budget + retry) ->
cache set -> respond, with /healthz (cheap, model-independent), /readyz
(Redis-aware), and /metrics.

Heavy deps (fastapi, redis, httpx, prometheus) are imported here, not in the pure
modules — so tests can exercise the logic without a running cluster.
"""

from __future__ import annotations

import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from . import load_gateway_cfg
from . import metrics as M
from .auth import verify_api_key
from .cache import ResponseCache, build_cache_key, is_cacheable
from .circuit_breaker import CircuitBreaker
from .concurrency import BoundedConcurrency
from .errors import (
    AuthFailed,
    BackendUnavailable,
    GatewayError,
    Overloaded,
    RateLimited,
    ValidationFailed,
    to_body,
)
from .model_client import ModelClient
from .rate_limit import RateLimiter
from .request_id import get_or_create_request_id
from .schemas import GenerateRequest, enforce_limits, to_model_payload

CFG = load_gateway_cfg()
API_KEY = os.environ.get("GATEWAY_API_KEY", "")


@asynccontextmanager
async def lifespan(app: FastAPI):
    import redis.asyncio as aioredis

    app.state.redis = aioredis.from_url(CFG["redis"]["url"], decode_responses=True)
    app.state.model = ModelClient.create(CFG)
    app.state.cache = ResponseCache(app.state.redis, CFG["cache"]["ttl_seconds"])
    app.state.limiter = RateLimiter(
        app.state.redis,
        CFG["rate_limit"]["requests_per_window"],
        CFG["rate_limit"]["window_seconds"],
    )
    app.state.breaker = CircuitBreaker(
        CFG["circuit_breaker"]["failure_threshold"],
        CFG["circuit_breaker"]["open_seconds"],
        CFG["circuit_breaker"]["half_open_probes"],
    )
    app.state.concurrency = BoundedConcurrency(
        CFG["concurrency"]["max_backend"], CFG["concurrency"]["queue_wait_seconds"]
    )
    try:
        yield
    finally:
        await app.state.model.aclose()
        await app.state.redis.aclose()


app = FastAPI(title="finbot gateway", lifespan=lifespan)


def _error_response(err: GatewayError, request_id: str) -> JSONResponse:
    headers = {CFG["request_id_header"]: request_id}
    retry_after = getattr(err, "retry_after", None)
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)
    return JSONResponse(status_code=err.status, content=to_body(err, request_id), headers=headers)


@app.get("/healthz")
async def healthz():
    # cheap + model-independent: never make liveness depend on the model
    return {"status": "ok"}


@app.get("/readyz")
async def readyz(request: Request):
    # rate limiting depends on Redis and is security-relevant -> not ready without it
    try:
        await request.app.state.redis.ping()
    except Exception:  # noqa: BLE001
        return JSONResponse(status_code=503, content={"status": "redis_unavailable"})
    return {"status": "ready"}


@app.get("/metrics")
async def metrics():
    data, content_type = M.render()
    return Response(content=data, media_type=content_type)


@app.post("/v1/generate")
async def generate(request: Request):
    app_ = request.app
    rid = get_or_create_request_id(request.headers.get(CFG["request_id_header"]))
    route = "/v1/generate"
    start = time.perf_counter()
    M.inflight.inc()
    try:
        # 1. authenticate
        if not verify_api_key(request.headers.get("Authorization"), API_KEY):
            raise AuthFailed()

        # 2. validate body + enforce config caps
        try:
            body = await request.json()
            req = GenerateRequest(**body)
        except ValidationFailed:
            raise
        except Exception as exc:
            raise ValidationFailed() from exc
        enforce_limits(req, CFG)

        # 3. rate-limit the caller (Redis failure -> security-first 503)
        if CFG["rate_limit"]["enabled"]:
            try:
                allowed, retry_after = await app_.state.limiter.check(API_KEY, time.time())
            except Exception as exc:
                raise Overloaded(retry_after=1) from exc
            if not allowed:
                M.rate_limit_rejections.inc()
                raise RateLimited(retry_after=retry_after)

        payload = to_model_payload(req)

        # 4. cache lookup (deterministic requests only; fail-open)
        cache_key = None
        if CFG["cache"]["enabled"] and is_cacheable(req.temperature, req.stream):
            cache_key = build_cache_key(
                payload, CFG["cache"]["schema_version"], CFG["cache"]["model_version"]
            )
            hit = await app_.state.cache.get(cache_key)
            if hit is not None:
                M.cache_events.labels(result="hit").inc()
                return _ok(hit, rid, cached=True)
            M.cache_events.labels(result="miss").inc()

        # 5. bounded concurrency (backpressure) -> 6. circuit breaker -> 7. model call
        async with app_.state.concurrency:
            M.set_breaker_state(app_.state.breaker.state.value)
            if not app_.state.breaker.allow():
                raise BackendUnavailable()
            M.backend_inflight.inc()
            b0 = time.perf_counter()
            try:
                result = await app_.state.model.complete(payload)
                app_.state.breaker.record_success()
                M.backend_requests.labels(outcome="ok").inc()
            except GatewayError:
                app_.state.breaker.record_failure()
                M.backend_requests.labels(outcome="error").inc()
                M.set_breaker_state(app_.state.breaker.state.value)
                raise
            finally:
                M.backend_inflight.dec()
                M.backend_duration.observe(time.perf_counter() - b0)

        content = result["choices"][0]["message"]["content"]
        usage = result.get("usage")
        body_out = {"content": content, "usage": usage, "model": result.get("model", "finbot")}

        # 8. cache the completed successful response when eligible
        if cache_key is not None:
            await app_.state.cache.set(cache_key, body_out)

        return _ok(body_out, rid, cached=False)

    except GatewayError as err:
        if isinstance(err, Overloaded):
            M.backpressure_rejections.inc()
        M.http_requests.labels(method="POST", route=route, status=err.status).inc()
        return _error_response(err, rid)
    except Exception:  # noqa: BLE001 - never leak a stack trace
        M.http_requests.labels(method="POST", route=route, status=500).inc()
        return _error_response(GatewayError(), rid)
    finally:
        M.inflight.dec()
        M.http_duration.labels(route=route).observe(time.perf_counter() - start)


def _ok(body_out: dict, rid: str, cached: bool) -> JSONResponse:
    M.http_requests.labels(method="POST", route="/v1/generate", status=200).inc()
    return JSONResponse(
        status_code=200,
        headers={CFG["request_id_header"]: rid},
        content={
            "request_id": rid,
            "model": body_out.get("model", "finbot"),
            "content": body_out["content"],
            "cached": cached,
            "usage": body_out.get("usage"),
        },
    )
