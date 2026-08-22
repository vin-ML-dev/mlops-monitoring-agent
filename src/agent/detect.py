"""Deterministic detection — classify healthy / degraded / down and list anomalies.

Pure function, NO LLM. Thresholds MIRROR the Day-6 alert rules so the agent and
Prometheus never disagree. This is the "detection" the guide insists must stay
deterministic; the LLM only explains the anomalies this produces.
"""

from __future__ import annotations


def classify(signals: dict, thresholds: dict) -> tuple[str, list[dict]]:
    """Return (serving_mode, anomalies) from collected signals + probe results.

    signals may include: gateway_reachable, model_reachable, model_replicas,
    p95_latency, error_ratio, breaker_state, pod_restarts. Missing signals are
    skipped (None) rather than assumed bad.
    """
    anomalies: list[dict] = []

    gw = signals.get("gateway_reachable")
    model_ok = signals.get("model_reachable")
    replicas = signals.get("model_replicas")

    # DOWN: gateway unreachable, or the model is unreachable / has no replicas
    gateway_down = gw is False
    model_down = (model_ok is False) or (replicas is not None and replicas < 1)

    if gateway_down or model_down:
        if gateway_down:
            anomalies.append({"key": "gateway_down", "detail": "gateway unreachable"})
        if model_down:
            anomalies.append({"key": "model_down", "detail": "model unreachable / no replicas"})
        return "down", anomalies

    # DEGRADED: reachable but a quality/stability threshold is breached
    p95 = signals.get("p95_latency")
    if p95 is not None and p95 > thresholds["p95_latency_seconds"]:
        anomalies.append({"key": "high_latency", "detail": f"p95={p95:.1f}s"})

    er = signals.get("error_ratio")
    if er is not None and er > thresholds["backend_error_ratio"]:
        anomalies.append({"key": "high_errors", "detail": f"backend error ratio={er:.1%}"})

    br = signals.get("breaker_state")
    if br is not None and br >= thresholds["breaker_open_value"]:
        anomalies.append({"key": "breaker_open", "detail": "circuit breaker open"})

    rs = signals.get("pod_restarts")
    if rs is not None and rs > thresholds["pod_restarts_15m"]:
        anomalies.append({"key": "restart_churn", "detail": f"{int(rs)} restarts in 15m"})

    mode = "degraded" if anomalies else "healthy"
    return mode, anomalies
