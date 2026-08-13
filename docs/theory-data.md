# Day 1 — Data Curation: the theory (in plain language)

This is the "why" behind the code in `src/data/`. Read it once; it makes every
file obvious.

**Project:** a finance-education assistant, fine-tuned later from `Qwen/Qwen3-1.7B`.
**Today:** turn raw finance instruction data into a **clean, safe, versioned** dataset.

> Golden rule of MLOps: your model is only as good as your data, and only as safe
> as your worst record. Day 1 earns both.

---

## The pipeline in one line

```
ingest → curate → build → validate → split
```

Raw tickets come in; a clean, PII-free, train/val/test dataset comes out, with an
audit report along the way.

---

## 1. Ingest — get the data

We stream **`gbharti/finance-alpaca`** from Hugging Face. It's Alpaca format
(fields: `instruction`, `input`, `output`) and has **no category column**, so we
combine `instruction` (+ optional `input`) into the user message and treat
`output` as the answer. The repo also ships a small
**offline sample** so everything runs with no internet. Source is a switch in
`params.yaml` (`sample` or `hf`).

*Production idea:* your pipeline should run the same way on a bundled sample and
on the real feed. That makes it testable and reproducible.

## 2. Curate — filter + scrub

Two jobs happen here.

**a) Quality filters** (`quality_filters.py`) — six simple checks that drop bad rows:
- **refusal** — low-quality "As an AI, I cannot…" boilerplate.
- **truncation** — replies cut off mid-sentence.
- **echo** — the reply just parrots the question.
- **repetition** — the reply loops the same words.
- **language** — non-English rows (we keep English only).
- **length** — too short (no signal) or absurdly long (junk).

Each filter is a **pure function** → easy to unit-test. Bad rows are *dropped and
counted*, never silently mangled.

**b) PII scrubbing** — the safety-critical step. Finance data can still contain
personal data (emails, phones, order IDs, cards, SSNs). If that data reaches
training, the model can memorise and repeat it — a real privacy incident.

We use **two layers**:
- **Regex** (always on) for predictable shapes: email, phone, card, SSN, IP, order ID.
- **Presidio NER** (optional) for names/locations that have no fixed shape.

The key rule: **no single detector is perfect**, so the regex layer *always* runs,
even after Presidio. (Turn on Presidio with `make install-pii` and
`pii.use_presidio: true`.)

Curate also writes **`curation_report.json`** — how many rows were kept/dropped
and why, and how much PII was removed. That's your audit trail.

## 3. Build — chat format + honesty examples

Fine-tuning a chat model needs the **chat format**:

```json
{"messages": [
  {"role": "system", "content": "You are a helpful, honest support assistant..."},
  {"role": "user", "content": "Where is my order?"},
  {"role": "assistant", "content": "Let me check that for you..."}
]}
```

We also **inject a few honesty examples** — replies like *"I can't guarantee
returns"* or *"I'm not a licensed advisor, so I can't tell you what to buy."*

Why add refusals here when we *removed* refusals in step 2? Different things:
- We drop **low-quality boilerplate** refusals (bad data).
- We add **good honesty** examples on purpose (good behaviour to teach).

A finance bot that honestly says "I can't predict that / I'm not an advisor" is
far safer than one that confidently makes up predictions.

## 4. Validate — prove it's safe before use

Two checks, and the run **fails loudly** if either fails:
- **schema** — every record matches the chat contract (valid roles, non-empty text).
- **PII leak** — we re-scan all text; if any PII survived, the run exits non-zero.

A non-zero exit is what lets **CI block a bad dataset**. "Trust, but verify."

## 5. Split — train / test / validation (5000 / 1000 / 1000)

We split the data so we can train on one part and honestly measure on another.

**Default: a random split by fixed counts** (5000 / 1000 / 1000). We fetch a few
thousand extra rows so enough survive curation; extras are discarded. This needs no
label column and is the production-safe default. (finance-alpaca has no category,
so random is the right call here.) If the pool is smaller than requested — like the
tiny offline sample — the counts scale down proportionally so it still runs.

**Optional: stratified split.** If you set `split.stratify_by: category`, we keep
each category's proportion equal across splits. If that field is missing, we
automatically fall back to random and say so.

*Production idea:* stratify only when you have a meaningful label and the data is
small or imbalanced. Watch out for **leakage** (related rows split across train and
test) more than for stratification — that's the mistake that inflates test scores.

The split is **deterministic** (fixed seed) so it's reproducible.

---

## Versioning (DVC) — the provenance question

Git tracks *code*; **DVC** tracks *data + pipeline stages* (`dvc.yaml`). Running
`dvc repro` re-runs only the stages whose inputs changed, and records which inputs
produced which outputs — so months later you can answer: *"exactly which data
version produced model v1.2.0?"*

---

## The golden set

`data/golden/golden_set.jsonl` is a small, **frozen** set of prompts with reference
answers (including honesty cases). We create it now and never let it change, so it's
a stable yardstick for evaluating the model on later days.

---

## What you can say in an interview

- "PII removal is safety-critical: two layers, a regex backstop that always runs,
  and a **leak self-check that fails the pipeline** if any PII survives."
- "Bad data is dropped and counted against a schema; the pipeline exits non-zero so
  **CI can block a bad dataset**."
- "I default to a **random split**; I stratify only when a label exists and the data
  is imbalanced, and I watch for leakage."
- "Data is versioned with **DVC**, so I can trace any model back to its exact data."
