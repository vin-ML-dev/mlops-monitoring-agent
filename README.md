# mlops-monitoring-agent

An 8-day, laptop-runnable build of a **finance-education domain LLM platform**:
curate data → fine-tune `Qwen/Qwen3-1.7B` (QLoRA) → serve it **in-cluster on CPU**
via llama.cpp behind a FastAPI gateway → monitor it with Prometheus + Alertmanager
and a LangGraph explanation agent → ship it with Kubernetes + GitOps.

**This repo currently contains Day 1: data curation, versioning & repo foundations.**
Theory notes: [`docs/theory-data.md`](docs/theory-data.md).

---

## What Day 1 does

```
ingest → curate → build → validate → split
```

Raw finance instruction data (`gbharti/finance-alpaca`) → a clean, **PII-scrubbed**,
chat-formatted, train/test/validation dataset (**5000 / 1000 / 1000**), with an audit
report and a frozen golden eval set.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
make install          # install dependencies
make data             # run the full pipeline on the bundled sample
make test             # run the tests (the PII tests are the important ones)
```

Outputs:
- `data/interim/curated.jsonl` + `curation_report.json` (kept/dropped counts, PII removed)
- `data/interim/built.jsonl` (chat format + honesty examples)
- `data/processed/{train,val,test}.jsonl`

### Use the real dataset (5000 / 1000 / 1000)

Edit `params.yaml` → `ingest.source: hf`, then `make data`. It streams
`gbharti/finance-alpaca` (68,912 rows). We fetch **8000** so that enough survive
curation to fill the exact **5000 / 1000 / 1000** split; extras are discarded.

> Is 5000 too much? No — it's a lean, cost-friendly size for QLoRA on a 1.7B model:
> enough to learn the finance domain, small enough to train in ~1–2 hours on a
> rented GPU and avoid overfitting.

### Enable the Presidio NER PII layer (optional, recommended)

```bash
make install-pii      # presidio + spaCy model
```
Then set `pii.use_presidio: true` in `configs/data.yaml` and re-run `make data`.

### Data versioning (DVC)

```bash
git init && dvc init
dvc repro
```

---

## Repo layout

```
src/data/           the only module on Day 1
  ingest.py         stream gbharti/finance-alpaca (or bundled offline sample)
  quality_filters.py refusal / truncation / echo / repetition / language / length
  curate.py         combine instruction+input, apply filters + PII scrub
  build_dataset.py  chat format + finance honesty examples
  validate.py       schema + PII-leak check (fails the run on any leak)
  split.py          fixed-count split 5000/1000/1000 (random; auto-scales if pool is small)
configs/data.yaml   filter thresholds, PII types, build + split settings
params.yaml         DVC knobs (seed, ingest source, split counts)
dvc.yaml            the pipeline stages
data/raw/           bundled finance sample + (later) streamed data
data/golden/        frozen eval set
docs/theory-data.md the "why" behind the pipeline
```

## Model & data

- Base model: **`Qwen/Qwen3-1.7B`** (fine-tuned on Day 2 with QLoRA).
- Data: **`gbharti/finance-alpaca`** (Alpaca format: instruction/input/output; no category) + curated honesty examples.

## License

Code: MIT (educational). The dataset and model carry their own licenses — check
their Hugging Face cards before commercial use.
