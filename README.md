# finbot — a finance-education LLM platform (MLOps, end to end)

A small **finance-education assistant** built the production way: curate data →
fine-tune `Qwen/Qwen3-1.7B` (QLoRA) → gate it on quality → **serve it in-cluster on CPU** →
(next) put a gateway in front and monitor it. This repo covers **Days 1–4**.

- **Base model:** `Qwen/Qwen3-1.7B` · **Data:** curated `gbharti/finance-alpaca` + honesty examples
- **Model (GGUF, gate-passed):** `vinmlops/finbot-qwen3-1.7b-gguf`

```
Day 1  DATA     ingest → curate (quality + PII) → build → validate → split
Day 2  TRAIN    QLoRA fine-tune → merge → push (model + GGUF) to the Hub
Day 3  GATE     score the GGUF vs a golden set → pass/fail → register a version
Day 4  SERVE    run the GGUF in-cluster on CPU (llama.cpp on Kubernetes)          ← this repo
Day 5+ GATEWAY· FastAPI + Redis → Prometheus + Alertmanager + a monitoring agent
```

> **Model status:** v1 **baseline** — coherent with working honesty guardrails, but verbose and
> not always accurate on fine details (quality is bounded by the forum-sourced data). Day 3
> quantifies that objectively.

---

## Day 4 — in-cluster serving (this repo's focus)

Turn the registered GGUF into a **live Kubernetes service**: self-healing, health-probed,
resource-limited, reachable at a stable in-cluster address (**`llama-cpp-svc:8080`**) — serving on
**CPU** with an **OpenAI-compatible API** (`POST /v1/chat/completions`).

```
build image → load into kind → apply manifests → pod downloads + loads the model → serve
```

**What makes it production-shaped**

- **Deployment** — self-healing (k8s restarts a crashed pod).
- **ClusterIP Service** (`llama-cpp-svc:8080`) — the stable address the Day 5 gateway will call.
- **ConfigMap + Secret** — model repo/threads and the HF token externalized (same image everywhere).
- **Three probes** — a **startupProbe** for the slow model load, **readiness** to gate traffic,
  **liveness** to trigger restarts.
- **Resource requests/limits** — CPU inference gets its own budget.

**How the model gets in:** the image is model-free; at startup the container downloads the
registered GGUF from the Hub (`fetch_model.py`) and launches llama.cpp.

---

## Run Day 4 (raw kubectl — quickest path)

Needs **Docker + kind + kubectl**. Run from the repo root.

```bash
# --- create the local cluster ---
kind create cluster --name finbot --config deploy/kind-cluster.yaml
kubectl get nodes                              # one node, STATUS = Ready

# --- build the model-server image + load it into kind ---
docker build -f serving/Dockerfile -t finbot-model:v1.0.0 .
kind load docker-image finbot-model:v1.0.0 --name finbot

# --- namespace + HF token secret (to pull the private GGUF) ---
kubectl apply -f deploy/namespace.yaml
export HF_TOKEN=hf_your_token
kubectl -n finbot create secret generic hf-token \
  --from-literal=HF_TOKEN="$HF_TOKEN" \
  --dry-run=client -o yaml | kubectl apply -f -

# or from .env

kubectl -n finbot create secret generic hf-token \
  --from-env-file=.env \
  --dry-run=client -o yaml | kubectl apply -f -

# --- deploy config, the model, and the service ---
kubectl apply -f deploy/configmap.yaml
kubectl apply -f deploy/deployment.yaml
kubectl apply -f deploy/service.yaml

# --- verify ---
kubectl -n finbot get all
kubectl -n finbot get pods -w                  # wait for 1/1 Running, then Ctrl-C
kubectl -n finbot get endpoints llama-cpp-svc  # should list a pod IP:8080 (not <none>)

# --- use it ---
kubectl -n finbot port-forward svc/llama-cpp-svc 8080:8080 &
curl http://localhost:8080/v1/chat/completions -H 'Content-Type: application/json' \
  -d '{"model":"finbot","messages":[{"role":"user","content":"What is an ETF?"}],"max_tokens":150}'

# --- delete ---
kind delete cluster --name finbot
```

**First start is slow:** the pod sits at `0/1` while it downloads (~1.8 GB) and loads the model —
the **startupProbe** is what keeps k8s from killing it during that wait. Watch progress with:
```bash
kubectl -n finbot logs -l app=finbot-model -f   # [fetch] downloading... then [serve] launching...
```

*(Prefer `make`? `make cluster-up`, `make image`, `make deploy`, `make status`, `make port-forward`,
`make smoke` do the same steps — see `make help`.)*

---

## Days 1–3 (recap — what this serves)

**Day 1 — Data.** `ingest → curate → build → validate → split`, two-layer PII scrubbing with a
**leak check that fails the pipeline**, DVC + `data-v1` tags. → 5000/1000/1000 splits.

**Day 2 — Fine-tuning.** QLoRA on a single 12 GB GPU, MLflow-tracked with the data version, merged
and pushed, then exported to a **q8_0 GGUF** for CPU serving.

**Day 3 — Eval gate.** Score the quantized GGUF against a frozen golden set; **stricter bar for
safety-critical honesty**; a non-zero exit **blocks a bad model**; approved models registered with
a **semver + provenance** (`v1.0.0`).

---

## Repo layout

```
src/data/         Day 1 — data pipeline
src/training/     Day 2 — QLoRA fine-tune / merge / push / GGUF
src/evaluation/   Day 3 — metrics / gate / register
src/serving/      Day 4 — fetch_model / payload / client
serving/          Day 4 — Dockerfile + entrypoint (the model-server image)
deploy/           Day 4 — kind-cluster / namespace / configmap / secret / deployment / service
configs/          data.yaml · train.yaml · eval.yaml · serve.yaml
docs/             theory-*.md (data / training / evaluation / serving)
tests/            offline tests (no cluster/model needed)
Makefile          self-documenting targets (make help)
```

## Quickstart (no cluster needed)

```bash
python3 -m venv myvenv && source myvenv/bin/activate
make install
make test            # config + payload + all k8s manifests validated offline
```

## Requirements

- **Python 3.11+.** `pip install -e ".[dev]"`; add `.[serve]` for the smoke client.
- **Day 4 runtime tools (not pip):** Docker, [kind](https://kind.sigs.k8s.io/), kubectl.
- Serving is **CPU-only** — no GPU needed once the model is trained.

---

## Troubleshooting Day 4

| Symptom | Cause / fix |
|---|---|
| Pod stuck `0/1`, logs show `[fetch] downloading` | Normal — downloading ~1.8 GB. Wait; watch `kubectl -n finbot logs -f`. |
| `ImagePullBackOff` | You skipped `kind load docker-image`. |
| `CrashLoopBackOff`, logs show a download error | `HF_TOKEN` missing/invalid or wrong `GGUF_REPO`/`GGUF_FILE`. |
| `docker build` fails on `llama-cpp-python` | `python:3.11-slim` lacks a compiler — add `build-essential cmake` in the Dockerfile. |
| `unrecognized arguments: --metrics` | `llama-cpp-python`'s server has no `--metrics` flag (that's the native server). Remove it; metrics are wired on Day 6. |
| Config/secret edit didn't take effect | ConfigMap/Secret changes don't auto-restart pods: `kubectl -n finbot rollout restart deployment/finbot-model`. |

---

## What each day proves

- **Day 1:** PII scrubbing with a pipeline-failing leak check; versioned, schema-validated data.
- **Day 2:** QLoRA on a small GPU; MLflow provenance; merged model + quantized GGUF shipped.
- **Day 3:** an automated **quality gate** with a stricter safety bar and a versioned registry.
- **Day 4:** the model as a **self-healing Kubernetes service** on CPU, OpenAI-compatible, with
  startup/readiness/liveness probes and externalized config/secrets.

---
