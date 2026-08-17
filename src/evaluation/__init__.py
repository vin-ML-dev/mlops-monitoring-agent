"""Day 3 evaluation module: score the model against the golden set, gate on
thresholds, and register an approved version.

Shared paths + a config loader. Heavy imports (llama_cpp) live inside the
functions that need them, so this package imports fine on a plain CPU machine
(and in tests) without the GGUF runtime installed.
"""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
EVAL_CFG_FILE = ROOT / "configs" / "eval.yaml"


def load_eval_cfg() -> dict:
    with open(EVAL_CFG_FILE, encoding="utf-8") as fh:
        return yaml.safe_load(fh)
