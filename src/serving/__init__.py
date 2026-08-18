"""Day 4 serving module: download the GGUF and serve it on CPU (llama.cpp,
OpenAI-compatible API), deployed in-cluster on Kubernetes.

Config loader + shared paths. Heavy/optional imports (huggingface_hub, requests)
live inside the functions that use them, so this package imports anywhere.
"""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SERVE_CFG_FILE = ROOT / "configs" / "serve.yaml"


def load_serve_cfg() -> dict:
    with open(SERVE_CFG_FILE, encoding="utf-8") as fh:
        return yaml.safe_load(fh)
