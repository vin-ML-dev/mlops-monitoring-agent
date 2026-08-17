# finbot — a finance-education LLM platform (MLOps, end to end)

Building a small **finance-education assistant** the production way: curate data →
fine-tune `Qwen/Qwen3-1.7B` (QLoRA) → **gate it on quality before release** → serve it
in-cluster on CPU → monitor it. This repo currently covers **Days 1–3**.

- **Base model:** `Qwen/Qwen3-1.7B` · **Data:** curated `gbharti/finance-alpaca` + honesty examples
- **Model (merged):** `vinmlops/finbot-qwen3-1.7b-baseline` · **GGUF (CPU-servable):** `vinmlops/finbot-qwen3-1.7b-gguf`

```
Day 1  DATA      ingest → curate (quality + PII) → build → validate → split
Day 2  TRAIN     QLoRA fine-tune → merge → push (model + GGUF) to the Hub
Day 3  GATE      score the GGUF vs a golden set → pass/fail → register a version   ← this repo
Day 4+ SERVE ·   in-cluster llama.cpp (CPU) → gateway → Prometheus + agent monitoring
```

> **Model status:** v1 **baseline** — coherent with working honesty guardrails, but verbose
> and not always accurate on fine details, because quality is bounded by the forum-sourced
> data. Day 3 exists to **quantify** that objectively instead of eyeballing it.

---

## Day 3 — the evaluation gate (this repo's focus)

Replace "the answers looked fine" with an **automated pass/fail decision**. Score the
**quantized GGUF** (the exact artifact served) against a frozen golden set; block anything
that doesn't clear the bar; register approved models with a version + provenance.

```
score → threshold check → PASS (register vX.Y.Z) | FAIL (exit 1, blocks the pipeline)
```

**Run it**

```bash
make install-eval                    # GGUF runtime (CPU)
make gate                            # score the GGUF, apply thresholds, exit 0/1
make register VERSION=v1.0.0         # record an APPROVED model (refuses if the gate failed)
make gate-test                       # prove the gate blocks a bad model (no GPU/GGUF needed)
```

**What makes it a real gate**

- **Frozen golden set** (`data/golden/golden_set.jsonl`) — CONCEPT items (expected keywords)
  + HONESTY traps (`must_refuse`). Frozen so scores are comparable over time.
- **Deterministic metrics** (`src/evaluation/metrics.py`) — refusal/prediction checks for
  honesty; length + keyword-coverage + no-hallucinated-links for concepts.
- **Higher bar for safety** — honesty pass-rate threshold (0.80) is stricter than overall
  correctness (0.60). A finance bot may fumble a definition; it must never guarantee returns.
- **A non-zero exit blocks deploy** (`src/evaluation/gate.py`) — the gate is a wall, not a report.
- **Versioned registry with provenance** (`src/evaluation/register.py`) — semver + git sha +
  **data version** (`data-v1`) + the scores it passed with; refuses to register a failed model.

---

## Days 1–2 (recap — the pipeline this builds on)

**Day 1 — Data.** `ingest → curate → build → validate → split`. Two-layer PII scrubbing
(regex backstop always on + optional Presidio restricted to *sensitive* entities only),
a **PII-leak check that fails the pipeline**, and DVC + `data-v1` tags so every model
traces to its exact data. → `data/processed/{train,val,test}.jsonl` (5000/1000/1000).

**Day 2 — Fine-tuning.** QLoRA (4-bit NF4 + LoRA) on a single 12 GB GPU, MLflow-tracked
with the data version, merged and pushed to the Hub, then exported to a **q8_0 GGUF** for
CPU serving. Honesty behaviour injected at the data layer; anti-repetition decoding and
Qwen3 thinking-mode-off learned the hard way.

---

## Repo layout

```
src/data/           Day 1 — ingest / quality_filters / curate / build_dataset / validate / split
src/training/       Day 2 — train / merge / push_to_hub / convert_gguf / model_card / mlflow_utils
src/evaluation/     Day 3 — metrics / gguf_runner / evaluate / gate / register
configs/            data.yaml (Day 1) · train.yaml (Day 2) · eval.yaml (Day 3)
data/golden/        golden_set.jsonl — the frozen exam
docs/               theory-data.md · theory-training.md · theory-evaluation.md
tests/              offline tests (no GPU/GGUF needed)
models_registry.json  approved model versions + provenance
Makefile            self-documenting targets (make help)
```

## Quickstart

```bash
python3 -m venv myvenv && source myvenv/bin/activate
make install          # core + dev + pre-commit
make gate-test        # see the gate logic pass (no model needed)
# with a real GGUF present or configured:
make install-eval && make gate
```

## Requirements

- **Python 3.11+.** `pip install -e ".[dev]"`; add `.[eval]` for the GGUF runtime (`llama-cpp-python`).
- **Day 3 runs on CPU** — no GPU needed to evaluate the quantized model.
- Pre-commit runs ruff (lint + format) on every commit.

---

## What each day proves

- **Day 1:** PII scrubbing with a **pipeline-failing leak check**; schema-validated, versioned data.
- **Day 2:** QLoRA on a small GPU; MLflow with data-version provenance; merged model + quantized GGUF shipped with an honest card.
- **Day 3:** a **quality gate** — frozen golden set, deterministic metrics, a **stricter safety bar**, a non-zero exit that **blocks a bad model**, and a **versioned registry with provenance**.
