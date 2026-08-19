# finbot — a finance-education LLM platform (MLOps, end to end)

A small **finance-education assistant** built the production way: curate data →
fine-tune `Qwen/Qwen3-1.7B` (QLoRA) → gate it on quality → serve it in-cluster on CPU →
**put a resilient gateway in front** → (next) monitor it. This repo covers **Days 1–5**.

```
Day 1  DATA     ingest → curate (quality + PII) → build → validate → split
Day 2  TRAIN    QLoRA fine-tune → merge → push (model + GGUF) to the Hub
Day 3  GATE     score the GGUF vs a golden set → pass/fail → register a version
Day 4  SERVE    run the GGUF in-cluster on CPU (llama-cpp-svc)
Day 5  GATEWAY  resilient FastAPI gateway + Redis in front of the model            ← this repo
Day 6+ MONITOR  Prometheus + Alertmanager
```

---

## Day 5 — the resilient gateway (this repo's focus)

Clients never call the model directly. A **FastAPI gateway** (Node A) treats the CPU model as a
**slow, capacity-limited, failure-prone dependency** and makes failure **bounded, fast,
observable, predictable, and contained**.

```
CLIENT → fastapi-gateway-svc:8000 → llama-cpp-svc:8080
         auth · validation · request IDs · rate limit (Redis) · cache (Redis) ·
         bounded concurrency · timeout budget · conservative retry ·
         circuit breaker · SSE · /healthz /readyz /metrics
```

**What's implemented (every concept from the Day 5 theory guide)**

- **Auth** — API key, constant-time compare, never logged.
- **Validation** — Pydantic + config caps (messages, length, max_tokens) reject bad requests
  before they cost inference.
- **Rate limiting** — Redis fixed-window per caller (keyed by a fingerprint, not the raw key);
  `429` + `Retry-After`. Redis down → security-first `503`.
- **Caching** — Redis, versioned canonical SHA-256 keys, **deterministic-only** (temp 0);
  fail-open; invalidation by version prefix.
- **Backpressure** — bounded per-pod concurrency to the model; no permit in time → `503`.
- **Timeout budget** — connect/read/write/pool (not one magic number).
- **Conservative retry** — at most one, transient pre-response failures only, never mid-stream.
- **Circuit breaker** — local per-process `closed → open → half-open → closed`; counts backend
  5xx, **not** client 4xx.
- **Error taxonomy** — 401 / 422 / 429 / 503 / 504 / 500 with structured bodies (no stack traces).
- **Observability** — `/healthz` (cheap, **model-independent** — no cascading restarts),
  `/readyz` (Redis-aware), `/metrics` (gateway boundary instrumented separately from the model
  boundary, ready for Day 6).

**Redis (`redis-svc`)** holds the cache + rate-limit state (agent state comes later). The circuit
breaker stays **local** on purpose — a Redis outage can't disable protection.

---

## Run Day 5

**Locally (docker-compose — gateway + Redis):**
```bash
export GATEWAY_API_KEY=dev-key
make up                     # builds + runs gateway + redis
# point the gateway at a reachable model (e.g. port-forward llama-cpp-svc)
```

**On the cluster (needs Day 4's model already deployed):**
```bash
make gw-image && make gw-load          # build + load the gateway image into kind
export GATEWAY_API_KEY=your-strong-key
make gw-secret                         # API-key secret
make gw-deploy                         # redis + gateway + service + hpa
make gw-status                         # pods/svc/hpa
make gw-forward &                      # localhost:8000 -> the gateway
make gw-smoke                          # send a request through the gateway
make gw-metrics                        # see the Prometheus metrics
```

**Offline (no cluster/Redis needed):**
```bash
make install && make test              # 18 unit tests: breaker, auth, cache, rate-limit, backpressure...
```

---

## Days 1–4 (recap — what the gateway fronts)

**Day 1 — Data.** curate + two-layer PII scrub + a leak check that fails the pipeline; DVC + `data-v1`.
**Day 2 — Fine-tune.** QLoRA on a 12 GB GPU, MLflow provenance, merged + q8_0 GGUF pushed.
**Day 3 — Gate.** score the GGUF vs a frozen golden set; stricter safety bar; non-zero exit blocks;
register `v1.0.0`.
**Day 4 — Serve.** the GGUF as a self-healing Kubernetes service (`llama-cpp-svc`) on CPU,
OpenAI-compatible, with startup/readiness/liveness probes.

---

## Repo layout

```
src/gateway/      Day 5 — app / schemas / auth / model_client / cache / rate_limit /
                          concurrency / circuit_breaker / errors / metrics / request_id
gateway/          Day 5 — Dockerfile (the gateway image)
deploy/           Day 5 — redis + gateway (configmap / secret / deployment / service / hpa)
configs/          gateway.yaml (timeouts, retry, breaker, cache, rate-limit, validation)
docs/             DAY5_THEORY_GUIDE.md
tests/            offline tests (no cluster/Redis needed)
docker-compose.yaml   local dev: gateway + redis
Makefile          self-documenting targets (make help)
```

## Requirements

- **Python 3.11+.** `pip install -e ".[dev]"`; add `.[gateway]` to run the gateway.
- **Runtime tools (not pip):** Docker, kind, kubectl.
- The gateway is **pure Python** (no native build); Redis + the model run as their own services.

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `/v1/generate` → 401 | Missing/wrong `Authorization: Bearer <GATEWAY_API_KEY>`. |
| `/v1/generate` → 503 (`OVERLOADED`) | Backpressure — all backend permits busy. Expected under load. |
| `/v1/generate` → 503 (`MODEL_UNAVAILABLE`) | Breaker open or connect failure — the model is down/restarting. |
| `/readyz` → 503 | Redis unavailable (rate limiting can't be enforced). |
| Gateway not scaling | HPA needs metrics-server installed in the cluster. |

---

## What each day proves

- **Day 1–4:** versioned data, gated model, self-healing CPU serving.
- **Day 5:** a **resilient application boundary** — the model is treated as an unreliable
  dependency, and slowness/restarts degrade **predictably** (bounded waits, clean 503s, an
  automatically-recovering circuit breaker) instead of cascading through the platform

---
