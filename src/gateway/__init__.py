"""Day 5 FastAPI gateway: a resilient application boundary in front of the
in-cluster CPU model (llama-cpp-svc:8080).

Config loader + shared paths. Heavy deps (fastapi, httpx, redis, prometheus) are
imported inside the modules/functions that use them, so the pure-logic modules
(circuit breaker, cache-key, rate-limit math, auth, errors) import with only the
standard library and are testable without a running cluster.
"""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
GATEWAY_CFG_FILE = ROOT / "configs" / "gateway.yaml"


def load_gateway_cfg() -> dict:
    with open(GATEWAY_CFG_FILE, encoding="utf-8") as fh:
        return yaml.safe_load(fh)
