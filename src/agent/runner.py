"""Agent entrypoint — build clients, start the /metrics server (heartbeat), and
loop: pick the cycle type (poll / canary / daily) and run one graph cycle.

Uses the LangGraph graph when available, else the sequential pipeline (identical
behaviour). The heartbeat is emitted at the end of every cycle regardless.
"""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime

from . import heartbeat, load_agent_cfg
from .canary import DEFAULT_CANARY_CASES, evaluate_cases
from .incident_store import IncidentStore
from .llm import Explainer
from .nodes import make_ctx
from .probes import Probes
from .prometheus_client import PromQL


class GatewayCanary:
    """Runs the canary prompts through the REAL gateway and scores deterministically."""

    def __init__(self, gateway_base: str, api_key: str, cases=None):
        self.gateway_base = gateway_base.rstrip("/")
        self.api_key = api_key
        self.cases = cases or DEFAULT_CANARY_CASES

    def run(self) -> list[dict]:
        import requests

        responses = {}
        for c in self.cases:
            try:
                r = requests.post(
                    f"{self.gateway_base}/v1/generate",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "messages": [{"role": "user", "content": c["prompt"]}],
                        "max_tokens": 128,
                        "temperature": 0,
                    },
                    timeout=60,
                )
                responses[c["name"]] = r.json().get("content", "") if r.status_code == 200 else ""
            except Exception:  # noqa: BLE001 - a failed call scores as empty (fails the case)
                responses[c["name"]] = ""
        return evaluate_cases(responses, self.cases)


def _build_ctx(cfg):
    import redis as _redis

    prom = PromQL(cfg["prometheus"]["base_url"])
    probes = Probes()
    store = IncidentStore(_redis.from_url(cfg["redis"]["url"], decode_responses=True))
    explainer = Explainer(cfg)
    from .notify import SlackNotifier

    slack = SlackNotifier(os.environ.get("SLACK_WEBHOOK"))
    canary = GatewayCanary(
        cfg["gateway"]["base_url"], os.environ.get(cfg["canary"]["api_key_env"], "")
    )
    return make_ctx(cfg, prom, probes, store, explainer, slack, canary)


def _pick_cycle(cfg, last_canary: float, last_daily_day: int) -> tuple[str, float, int]:
    now = time.time()
    today = datetime.now(UTC).timetuple().tm_yday
    hour = datetime.now(UTC).hour
    if hour == cfg["schedule"]["daily_hour_utc"] and today != last_daily_day:
        return "daily", last_canary, today
    if now - last_canary >= cfg["schedule"]["canary_interval_seconds"]:
        return "canary", now, last_daily_day
    return "poll", last_canary, last_daily_day


def main() -> None:
    cfg = load_agent_cfg()
    heartbeat.serve_metrics(cfg["metrics_port"])
    ctx = _build_ctx(cfg)

    # prefer the LangGraph graph; fall back to the sequential pipeline
    try:
        from .graph import build_graph

        graph = build_graph(ctx)

        def run(cycle_type):
            graph.invoke({"cycle_type": cycle_type, "now": time.time(), "diagnosis": []})
    except Exception:  # noqa: BLE001 - langgraph missing/unavailable -> sequential runner
        from .pipeline import run_cycle

        def run(cycle_type):
            run_cycle(ctx, cycle_type)

    last_canary = 0.0
    last_daily_day = -1
    poll = cfg["schedule"]["poll_interval_seconds"]
    while True:
        cycle_type, last_canary, last_daily_day = _pick_cycle(cfg, last_canary, last_daily_day)
        try:
            run(cycle_type)
        except Exception as exc:  # noqa: BLE001 - never die on one bad cycle; heartbeat still beats
            print(f"[agent] cycle error ({cycle_type}): {exc}", flush=True)
            heartbeat.beat()
        time.sleep(poll)


if __name__ == "__main__":
    main()
