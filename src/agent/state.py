"""AgentState — the working memory carried through one agent cycle.

Mirrors the fields in the Day-7 guide. total=False so nodes can populate it
incrementally.
"""

from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    cycle_type: str  # poll | canary | daily
    now: float  # unix time of this cycle
    metrics: dict[str, Any]  # PromQL signals collected this cycle
    gateway_reachable: bool
    model_reachable: bool
    serving_mode: str  # healthy | degraded | down
    anomalies: list[dict]  # deterministic anomalies detected this cycle
    open_incidents: dict  # incidents known from Redis
    recoveries: list[str]  # incident keys that just recovered
    diagnosis: list[dict]  # messages to send (incident/recovery/canary/daily)
    notifications: list[str]  # keys actually notified
    daily_stats: dict[str, Any]
    canary_results: list[dict]
    _correlation: dict  # internal: correlate() output
