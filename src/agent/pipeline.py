"""Sequential cycle runner — the same nodes as the LangGraph graph, wired in plain
Python so the whole flow is testable without langgraph. graph.py is the "official"
LangGraph implementation; both call the identical node functions in nodes.py.
"""

from __future__ import annotations

import time

from . import nodes


def run_cycle(ctx, cycle_type: str = "poll", now: float | None = None) -> dict:
    state: dict = {"cycle_type": cycle_type, "now": now or time.time(), "diagnosis": []}

    state.update(nodes.fetch_metrics(state, ctx))
    state.update(nodes.probe_services(state, ctx))
    state.update(nodes.detect_anomalies(state, ctx))

    if cycle_type == "daily":
        state.update(nodes.build_daily_report(state, ctx))
    elif cycle_type == "canary":
        state.update(nodes.run_canary(state, ctx))
    else:  # poll
        state.update(nodes.correlate_incidents(state, ctx))
        state.update(nodes.diagnose(state, ctx))

    state.update(nodes.notify(state, ctx))
    state.update(nodes.persist(state, ctx))
    return state
