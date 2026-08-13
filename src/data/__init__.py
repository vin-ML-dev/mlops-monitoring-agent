"""Day 1 data module: ingest -> curate -> build -> validate -> split.

Shared file paths and tiny config loaders so every step reads the same settings
and writes to the same places.
"""

from __future__ import annotations

from pathlib import Path

import yaml

# repo root = two levels up from this file (src/data/__init__.py -> repo/)
ROOT = Path(__file__).resolve().parents[2]

PARAMS_FILE = ROOT / "params.yaml"
DATA_CFG_FILE = ROOT / "configs" / "data.yaml"

#RAW_SAMPLE = ROOT / "data" / "raw" / "finance_sample.jsonl"
GOLDEN = ROOT / "data" / "golden" / "golden_set.jsonl"

INTERIM = ROOT / "data" / "interim"
INGESTED = INTERIM / "ingested.jsonl"
CURATED = INTERIM / "curated.jsonl"
REPORT = INTERIM / "curation_report.json"
BUILT = INTERIM / "built.jsonl"
VALIDATED = INTERIM / "validated.jsonl"

PROCESSED = ROOT / "data" / "processed"
TRAIN = PROCESSED / "train.jsonl"
VAL = PROCESSED / "val.jsonl"
TEST = PROCESSED / "test.jsonl"


def load_params() -> dict:
    """DVC pipeline knobs (seed, ingest source, split ratios)."""
    with open(PARAMS_FILE, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_data_cfg() -> dict:
    """Curation rules (filter thresholds, PII types, build + split settings)."""
    with open(DATA_CFG_FILE, encoding="utf-8") as fh:
        return yaml.safe_load(fh)
