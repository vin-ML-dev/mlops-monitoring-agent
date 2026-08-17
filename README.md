# finbot — a finance-education LLM platform (MLOps, end to end)

Building a small **finance-education assistant** the production way: curate data →
fine-tune `Qwen/Qwen3-1.7B` (QLoRA) → serve it **in-cluster on CPU** via llama.cpp →
monitor it with Prometheus + Alertmanager and a LangGraph explanation agent → ship it
with Kubernetes + GitOps.

This repo currently covers **Day 1 (data)** and **Day 2 (fine-tuning + GGUF)**.

- **Base model:** `Qwen/Qwen3-1.7B`
- **Data:** curated [`gbharti/finance-alpaca`](https://huggingface.co/datasets/gbharti/finance-alpaca) + hand-written honesty examples
- **v1 model (merged):** `vinmlops/finbot-qwen3-1.7b-baseline`
- **v1 model (GGUF, CPU-servable):** `vinmlops/finbot-qwen3-1.7b-gguf`

> **Status:** v1 **baseline**. The model is coherent and its honesty guardrails work, but it
> can be verbose and isn't consistently accurate on fine details — because model quality is
> bounded by **data quality**, and finance-alpaca is forum-sourced and stylistically noisy.
> A future v2 focuses on cleaner data. Days 1–2 deliberately prioritize a complete, working,
> observable pipeline over peak accuracy.

---

## Quickstart

```bash
python3 -m venv myvenv && source myvenv/bin/activate
make install                 # core + dev deps (pyproject) + pre-commit hooks
make data                    # Day 1: build the dataset (dvc)
make test && make lint       # verify
```

`make help` lists every target.

---

## Day 1 — Data curation

Turn raw finance instructions into a **clean, PII-safe, versioned, tested** dataset.

```
ingest → curate → build → validate → split
```

- **ingest** — stream `gbharti/finance-alpaca` from Hugging Face (Alpaca format: `instruction` / `input` / `output`; no category column).
- **curate** — six quality filters (refusal / truncation / echo / repetition / language / length) + **PII scrubbing** (regex backstop always on + optional Presidio, restricted to *sensitive* entities only — never LOCATION/DATE_TIME/NRP, which are legitimate answer content).
- **build** — convert to chat format + inject curated **honesty examples** (refuse to predict prices / guarantee returns).
- **validate** — schema + **PII-leak self-check**; the run **fails (non-zero exit)** if any PII survives, so CI can block a bad dataset.
- **split** — random **80 / 10 / 10** into train / test / validation (finance-alpaca has no label, so random is correct).

**Run it**

```bash
make data                    # full pipeline via DVC (re-runs only what changed)
# or stage by stage:
make ingest  make curate  make build  make validate  make split
make install-pii             # optional: add Presidio NER + spaCy model
```

**Outputs**

- `data/interim/curated.jsonl` + `curation_report.json` (kept/dropped counts, PII removed)
- `data/interim/built.jsonl` (chat format + honesty examples)
- `data/processed/{train,val,test}.jsonl` — **5000 / 1000 / 1000**

**Versioning (DVC + git tags)**

```bash
git init && dvc init
dvc repro
git add . && git commit -m "Day 1: finance data curation pipeline"
make tag-data VERSION=data-v1        # freeze this data version
git push origin data-v1
```

The git tag (`data-v1`) flows into MLflow and the model card, so every model traces back to its exact data.

---

## Day 2 — QLoRA fine-tuning + GGUF export

Fine-tune `Qwen3-1.7B` with **QLoRA** on the Day 1 data, track with MLflow, merge the adapter,
push the model **and** a CPU-servable **GGUF** to Hugging Face. Trained on a single **12 GB GPU (RTX 3060)**.

```
train → merge → push (model) → gguf → push (gguf)
```

**Interactive path (recommended)** — the notebook has the real code in each cell and is version-resilient:

```bash
make notebook                # opens notebooks/day2_finance_qlora.ipynb
```

**Scripted path**

```bash
make train-setup             # install the QLoRA stack (needs a CUDA GPU)
make train                   # QLoRA fine-tune (checkpoint-safe; MLflow-tracked)
make mlflow-ui               # inspect runs at http://127.0.0.1:5000
make merge                   # adapter -> full bf16 model
make infer                   # quick sanity generations (incl. an honesty case)
make hf-login && make push-model
```

**GGUF export (CPU serving artifact — Day 4 loads this)**

> Run conversion in a **separate venv** — llama.cpp's requirements can otherwise downgrade
> `transformers`/`tokenizers` and break your training environment.

```bash
python3 -m venv ~/ggufenv && source ~/ggufenv/bin/activate
make gguf-setup              # clone llama.cpp + convert-script deps
make gguf-download           # pull the merged model from the Hub
make gguf                    # convert -> q8_0 GGUF (no build needed)
make gguf-smoke              # load it and generate one answer (proves CPU serving)
make push-gguf               # upload GGUF + card to the Hub
make tag-model VERSION=model-v1
```

### Key Day-2 settings (learned the hard way)

- **QLoRA:** 4-bit NF4 base + LoRA (r=16, alpha=32) → fine-tunes a 1.7B model in ~12 GB.
- **12 GB tuning:** `max_seq_len=1024`, batch 2 × grad-accum 8 (effective 16). OOM ladder in `configs/train.yaml`.
- **Eval + early stopping:** keeps the best epoch (val loss bottomed at epoch 2).
- **Qwen3 thinking mode OFF** (`enable_thinking=false`) — otherwise answers carry empty `<think>` blocks.
- **Anti-repetition decoding** for a small model: `temperature=0.3, top_p=0.9, repetition_penalty=1.2, no_repeat_ngram_size=4` (greedy decoding looped badly).
- **GGUF = q8_0** (the no-build path). `Q4_K_M` is smaller but needs the compiled `llama-quantize` binary.

---

## Repo layout

```
src/data/            Day 1: ingest / quality_filters / curate / build_dataset / validate / split
src/training/        Day 2: data / model / train / merge / push_to_hub / convert_gguf / infer / model_card / mlflow_utils
configs/data.yaml    Day 1 filter thresholds, PII types, split settings
configs/train.yaml   Day 2 QLoRA/LoRA/training/eval/inference/gguf settings
params.yaml          DVC knobs (seed, ingest, split)
dvc.yaml             the Day 1 pipeline stages
data/raw/ golden/    bundled inputs + frozen eval set
notebooks/           day2_finance_qlora.ipynb (the interactive fine-tune runbook)
docs/                theory-data.md, theory-training.md
tests/               offline tests (no GPU needed)
Makefile             self-documenting targets (make help)
```

---

## Requirements & environment

- **Python 3.11+.** Install with `pip install -e ".[dev]"` (extras: `.[pii]` for Presidio, training stack via `make train-setup`).
- **Day 1** runs on CPU (no GPU). **Day 2 training** needs a CUDA GPU (bf16 on Ampere+, e.g. RTX 30xx).
- **Qwen3** needs `transformers >= 4.51`. The notebook is version-resilient (it drops `SFTConfig`/`SFTTrainer` args your installed TRL doesn't accept).
- **Pre-commit** runs ruff (lint + format) and file-hygiene checks on every `git commit` (`pre-commit install`).

---

## What each day proves

- **Day 1:** two-layer PII scrubbing with a **leak check that fails the pipeline**; bad data dropped and counted against a schema; data versioned with DVC + tags so any model traces to its exact data; honesty behavior injected at the data layer.
- **Day 2:** QLoRA on a small GPU; MLflow tracking with the **data version**; checkpoint-safe training; merged model + **quantized GGUF** published with an honest model card; and the core lesson demonstrated empirically — **your model is only as good as your data.**
---
