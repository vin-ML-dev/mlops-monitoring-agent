"""Day 7 LangGraph monitoring agent (Node C) — the explanation layer.

Deterministic detection (mirroring Day 6) + LLM explanation only. Never
remediates. Heavy/optional deps (langgraph, redis, requests, prometheus_client)
are imported inside the modules/functions that use them, so the pure logic
(detect, correlate, canary scoring, the template explainer) imports and tests
without a cluster.
"""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
AGENT_CFG_FILE = ROOT / "configs" / "agent.yaml"


def load_agent_cfg() -> dict:
    with open(AGENT_CFG_FILE, encoding="utf-8") as fh:
        return yaml.safe_load(fh)
