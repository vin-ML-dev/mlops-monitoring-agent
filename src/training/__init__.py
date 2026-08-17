"""Day 2 training module: fine-tune Qwen3-1.7B with QLoRA on the Day 1 data.

Shared paths + a config loader. Heavy ML imports (torch, transformers, peft,
trl, bitsandbytes) live INSIDE the functions that need them, so this package
imports fine on a plain CPU machine (and in tests) without a GPU.
"""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
TRAIN_CFG_FILE = ROOT / "configs" / "train.yaml"


def load_train_cfg() -> dict:
    with open(TRAIN_CFG_FILE, encoding="utf-8") as fh:
        return yaml.safe_load(fh)
