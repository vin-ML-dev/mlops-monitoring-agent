"""The agent nodes. Each is a small function `(state, ctx) -> dict` (partial state
update). `ctx` bundles the clients + config so nodes are easy to test with fakes.

The SAME nodes are wired two ways: pipeline.py runs them sequentially (simple,
testable, no langgraph); graph.py wires them into a real LangGraph StateGraph.
"""

from __future__ import annotations

import time
from types import SimpleNamespace

from . import heartbeat
from .correlate import correlate
from .detect import classify


def make_ctx(cfg, prom, probes, store, explainer, slack, canary_runner=None) -> SimpleNamespace:
    return SimpleNamespace(
        cfg=cfg,
        prom=prom,
        probes=probes,
        store=store,
        explainer=explainer,
        slack=slack,
        canary_runner=canary_runner,
    )


# ---- nodes ----
def fetch_metrics(state: dict, ctx) -> dict:
    return {"metrics": ctx.prom.collect()}


def probe_services(state: dict, ctx) -> dict:
    return {
        "gateway_reachable": ctx.probes.gateway_reachable(ctx.cfg["gateway"]["base_url"]),
        "model_reachable": ctx.probes.model_reachable(ctx.cfg["model"]["base_url"]),
    }


def detect_anomalies(state: dict, ctx) -> dict:
    signals = dict(state.get("metrics") or {})
    signals["gateway_reachable"] = state.get("gateway_reachable")
    signals["model_reachable"] = state.get("model_reachable")
    mode, anomalies = classify(signals, ctx.cfg["thresholds"])
    return {"serving_mode": mode, "anomalies": anomalies}


def correlate_incidents(state: dict, ctx) -> dict:
    now = state.get("now") or time.time()
    open_inc = ctx.store.get_open_incidents()
    last = ctx.store.get_last_notified()
    result = correlate(state.get("anomalies", []), open_inc, now, ctx.cfg["cooldown_seconds"], last)
    return {"open_incidents": open_inc, "_correlation": result, "recoveries": result["recovered"]}


def diagnose(state: dict, ctx) -> dict:
    """LLM explains NEW/cooldown-elapsed incidents + recoveries. Reuses any prior diagnosis."""
    corr = state.get("_correlation", {})
    notes = list(state.get("diagnosis", []))
    for a in corr.get("to_notify", []):
        text = ctx.explainer.explain_incident(state["serving_mode"], [a], state.get("metrics", {}))
        heartbeat.LLM_CALLS.labels(reason="incident").inc()
        notes.append(
            {"kind": "incident", "key": a["key"], "mode": state["serving_mode"], "text": text}
        )
    for key in corr.get("recovered", []):
        notes.append({"kind": "recovery", "key": key, "text": f"{key} is back to normal."})
    return {"diagnosis": notes}


def run_canary(state: dict, ctx) -> dict:
    """Run known prompts through the gateway, score deterministically; LLM explains failures."""
    results = ctx.canary_runner.run() if ctx.canary_runner else []
    failures = [r for r in results if not r["passed"]]
    notes = list(state.get("diagnosis", []))
    if failures:
        text = ctx.explainer.explain_canary(failures)
        heartbeat.LLM_CALLS.labels(reason="canary").inc()
        notes.append({"kind": "canary", "text": text})
    return {"canary_results": results, "diagnosis": notes}


def build_daily_report(state: dict, ctx) -> dict:
    m = state.get("metrics") or {}
    stats = {
        "request_rate_per_s": round(m.get("request_rate") or 0, 3),
        "p95_latency_s": round(m.get("p95_latency") or 0, 2),
        "error_ratio": round(m.get("error_ratio") or 0, 4),
        "cache_hit_ratio": round(m.get("cache_hit_ratio") or 0, 3),
        "open_incidents": len(ctx.store.get_open_incidents()),
    }
    summary = ctx.explainer.summarize_daily(stats)
    heartbeat.LLM_CALLS.labels(reason="daily").inc()
    notes = list(state.get("diagnosis", []))
    notes.append({"kind": "daily", "text": summary})
    return {"daily_stats": stats, "diagnosis": notes}


def notify(state: dict, ctx) -> dict:
    sent = []
    now = state.get("now") or time.time()
    for n in state.get("diagnosis", []):
        kind = n["kind"]
        if kind == "incident":
            ctx.slack.notify_incident(n["key"], n.get("mode", "degraded"), n["text"])
            ctx.store.set_last_notified(n["key"], now)
        elif kind == "recovery":
            ctx.slack.notify_recovery(n["key"], n["text"])
        elif kind == "canary":
            ctx.slack.notify_canary(n["text"])
        elif kind == "daily":
            ctx.slack.notify_daily(n["text"])
        heartbeat.NOTIFICATIONS.labels(kind=kind).inc()
        sent.append(n.get("key", kind))
    return {"notifications": sent}


def persist(state: dict, ctx) -> dict:
    """Update open incidents in Redis and emit the heartbeat (every cycle)."""
    now = state.get("now") or time.time()
    prev = state.get("open_incidents", {})
    new_open = {}
    for a in state.get("anomalies", []):
        k = a["key"]
        new_open[k] = {
            "opened_at": prev[k]["opened_at"] if k in prev else now,
            "detail": a["detail"],
        }
    ctx.store.save_open_incidents(new_open)
    heartbeat.CYCLES.labels(cycle_type=state.get("cycle_type", "poll")).inc()
    heartbeat.beat()  # <-- arms the Day-6 dead-man switch
    return {"open_incidents": new_open}


__all__ = [
    "build_daily_report",
    "correlate_incidents",
    "detect_anomalies",
    "diagnose",
    "fetch_metrics",
    "make_ctx",
    "notify",
    "persist",
    "probe_services",
    "run_canary",
]
