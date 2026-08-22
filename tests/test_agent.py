"""Offline tests for the Day-7 agent (no cluster, no LLM, no Slack).

Covers the deterministic core (detect, correlate/cooldown, canary scoring, the
template explainer) and a full pipeline cycle driven by fake clients — proving
the healthy/incident/recovery/canary/daily flows without any real dependency.
"""

from __future__ import annotations

from src.agent import load_agent_cfg
from src.agent.canary import evaluate_cases, score_response
from src.agent.correlate import correlate
from src.agent.detect import classify
from src.agent.llm import Explainer
from src.agent.nodes import make_ctx
from src.agent.pipeline import run_cycle

CFG = load_agent_cfg()
TH = CFG["thresholds"]


# ---------------- detection (deterministic, mirrors Day 6) ----------------
def test_healthy_when_all_good():
    signals = {
        "gateway_reachable": True,
        "model_reachable": True,
        "model_replicas": 1,
        "p95_latency": 2.0,
        "error_ratio": 0.0,
        "breaker_state": 0,
        "pod_restarts": 0,
    }
    mode, anoms = classify(signals, TH)
    assert mode == "healthy" and anoms == []


def test_down_when_model_unreachable():
    signals = {"gateway_reachable": True, "model_reachable": False, "model_replicas": 0}
    mode, anoms = classify(signals, TH)
    assert mode == "down"
    assert any(a["key"] == "model_down" for a in anoms)


def test_down_when_gateway_unreachable():
    mode, anoms = classify({"gateway_reachable": False, "model_reachable": True}, TH)
    assert mode == "down"
    assert any(a["key"] == "gateway_down" for a in anoms)


def test_degraded_on_high_latency():
    signals = {
        "gateway_reachable": True,
        "model_reachable": True,
        "model_replicas": 1,
        "p95_latency": 30.0,
        "error_ratio": 0.0,
        "breaker_state": 0,
    }
    mode, anoms = classify(signals, TH)
    assert mode == "degraded"
    assert any(a["key"] == "high_latency" for a in anoms)


def test_degraded_on_breaker_open():
    signals = {
        "gateway_reachable": True,
        "model_reachable": True,
        "model_replicas": 1,
        "breaker_state": 2,
    }
    mode, anoms = classify(signals, TH)
    assert mode == "degraded"
    assert any(a["key"] == "breaker_open" for a in anoms)


def test_missing_signals_are_ignored_not_assumed_bad():
    # only reachability known -> healthy (no false anomalies from None metrics)
    mode, anoms = classify({"gateway_reachable": True, "model_reachable": True}, TH)
    assert mode == "healthy" and anoms == []


# ---------------- correlation + cooldown ----------------
def test_new_incident_is_flagged_and_notified():
    anoms = [{"key": "model_down", "detail": "x"}]
    r = correlate(anoms, open_incidents={}, now=1000, cooldown_seconds=900, last_notified={})
    assert [a["key"] for a in r["new"]] == ["model_down"]
    assert [a["key"] for a in r["to_notify"]] == ["model_down"]


def test_still_open_suppressed_within_cooldown():
    anoms = [{"key": "model_down", "detail": "x"}]
    r = correlate(
        anoms,
        open_incidents={"model_down": {"opened_at": 500}},
        now=1000,
        cooldown_seconds=900,
        last_notified={"model_down": 800},
    )
    assert r["to_notify"] == []  # 1000-800 < 900 -> suppressed
    assert [a["key"] for a in r["still_open"]] == ["model_down"]


def test_still_open_renotified_after_cooldown():
    anoms = [{"key": "model_down", "detail": "x"}]
    r = correlate(
        anoms,
        open_incidents={"model_down": {"opened_at": 0}},
        now=2000,
        cooldown_seconds=900,
        last_notified={"model_down": 1000},
    )
    assert [a["key"] for a in r["to_notify"]] == ["model_down"]  # 2000-1000 >= 900


def test_recovery_detected():
    r = correlate(
        [],
        open_incidents={"model_down": {"opened_at": 0}},
        now=1000,
        cooldown_seconds=900,
        last_notified={},
    )
    assert r["recovered"] == ["model_down"]


# ---------------- canary scoring (deterministic) ----------------
def test_canary_keyword_pass_and_fail():
    ok, _ = score_response(
        "An ETF is an exchange-traded fund.", {"type": "keyword", "any": ["etf", "fund"]}
    )
    assert ok is True
    bad, _ = score_response("I like turtles.", {"type": "keyword", "any": ["etf", "fund"]})
    assert bad is False


def test_canary_refusal():
    ok, _ = score_response("I can't predict which stock will double.", {"type": "refusal"})
    assert ok is True
    bad, _ = score_response("Buy TSLA, it will double.", {"type": "refusal"})
    assert bad is False


def test_evaluate_cases_marks_failures():
    responses = {"etf_concept": "an exchange traded fund", "honesty_refusal": "buy NVDA now"}
    results = evaluate_cases(responses)
    by = {r["name"]: r["passed"] for r in results}
    assert by["etf_concept"] is True and by["honesty_refusal"] is False


# ---------------- template explainer (no external LLM) ----------------
def test_template_explainer_is_deterministic_and_llm_free():
    ex = Explainer({"llm": {"backend": "template"}})
    txt = ex.explain_incident("down", [{"key": "model_down", "detail": "no replicas"}], {})
    assert "DOWN" in txt and "model pod" in txt


# ---------------- full pipeline with fakes (no cluster/LLM/Slack) ----------------
class FakeProm:
    def __init__(self, signals):
        self.signals = signals

    def collect(self):
        return self.signals


class FakeProbes:
    def __init__(self, gw=True, model=True):
        self.gw, self.model = gw, model

    def gateway_reachable(self, _):
        return self.gw

    def model_reachable(self, _):
        return self.model


class FakeStore:
    def __init__(self):
        self.open, self.notified = {}, {}

    def get_open_incidents(self):
        return dict(self.open)

    def save_open_incidents(self, d):
        self.open = dict(d)

    def get_last_notified(self):
        return dict(self.notified)

    def set_last_notified(self, k, ts):
        self.notified[k] = ts

    def get_daily_stats(self):
        return {}

    def save_daily_stats(self, s):
        pass


class FakeSlack:
    def __init__(self):
        self.msgs = []

    def notify_incident(self, key, mode, text):
        self.msgs.append(("incident", key))
        return True

    def notify_recovery(self, key, text):
        self.msgs.append(("recovery", key))
        return True

    def notify_canary(self, text):
        self.msgs.append(("canary", None))
        return True

    def notify_daily(self, text):
        self.msgs.append(("daily", None))
        return True


def _ctx(signals, gw=True, model=True):
    return make_ctx(
        CFG,
        FakeProm(signals),
        FakeProbes(gw, model),
        FakeStore(),
        Explainer({"llm": {"backend": "template"}}),
        FakeSlack(),
    )


def test_pipeline_healthy_sends_nothing():
    ctx = _ctx(
        {
            "p95_latency": 1.0,
            "error_ratio": 0.0,
            "breaker_state": 0,
            "model_replicas": 1,
            "pod_restarts": 0,
        }
    )
    state = run_cycle(ctx, "poll")
    assert state["serving_mode"] == "healthy"
    assert ctx.slack.msgs == []  # zero notifications on a healthy poll


def test_pipeline_new_incident_notifies_once():
    ctx = _ctx({"model_replicas": 0}, model=False)
    state = run_cycle(ctx, "poll")
    assert state["serving_mode"] == "down"
    assert ("incident", "model_down") in ctx.slack.msgs
    # second cycle: same incident, within cooldown -> suppressed
    ctx.slack.msgs.clear()
    run_cycle(ctx, "poll", now=state["now"] + 10)
    assert ctx.slack.msgs == []


def test_pipeline_recovery_notifies():
    ctx = _ctx({"model_replicas": 0}, model=False)
    s1 = run_cycle(ctx, "poll")  # incident opens
    # now healthy: swap the fakes to a good state
    ctx.prom = FakeProm(
        {
            "p95_latency": 1.0,
            "error_ratio": 0.0,
            "breaker_state": 0,
            "model_replicas": 1,
            "pod_restarts": 0,
        }
    )
    ctx.probes = FakeProbes(True, True)
    run_cycle(ctx, "poll", now=s1["now"] + 10)
    assert ("recovery", "model_down") in ctx.slack.msgs


def test_pipeline_daily_report_sends_summary():
    ctx = _ctx(
        {
            "request_rate": 5,
            "p95_latency": 3.0,
            "error_ratio": 0.0,
            "cache_hit_ratio": 0.4,
            "breaker_state": 0,
            "model_replicas": 1,
        }
    )
    run_cycle(ctx, "daily")
    assert ("daily", None) in ctx.slack.msgs


# ---------------- heartbeat metric name (arms the Day-6 rule) ----------------
def test_heartbeat_metric_has_the_day6_name():
    from src.agent import heartbeat

    heartbeat.beat()
    names = {"monitoring_agent_heartbeat_timestamp_seconds", "agent_heartbeat"}
    from prometheus_client import REGISTRY

    present = {m.name for m in REGISTRY.collect()}
    # timestamp gauge is the one the Day-6 AgentHeartbeatLost rule watches
    assert "monitoring_agent_heartbeat_timestamp_seconds" in present
    assert names <= present | {"monitoring_agent_heartbeat_timestamp"}  # gauge base name
