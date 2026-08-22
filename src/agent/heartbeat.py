"""Heartbeat + agent metrics, exposed on /metrics for Prometheus to scrape.

CRITICAL: the timestamp gauge is named `monitoring_agent_heartbeat_timestamp_seconds`
— the EXACT metric the Day-6 `AgentHeartbeatLost` rule watches. Emitting it every
cycle is what activates that dormant dead-man switch. The agent never watches its
own heartbeat; Prometheus + Alertmanager do.
"""

from __future__ import annotations

import time

from prometheus_client import Counter, Gauge, start_http_server

# what the Day-6 rule keys off (staleness form): time() - max(this) > 120
HEARTBEAT_TS = Gauge(
    "monitoring_agent_heartbeat_timestamp_seconds",
    "Unix time of the last completed agent cycle",
)
# simple liveness gauge (matches the diagram's `agent_heartbeat 1`)
HEARTBEAT = Gauge("agent_heartbeat", "1 while the agent is cycling")

CYCLES = Counter("agent_cycles_total", "Agent cycles run", ["cycle_type"])
LLM_CALLS = Counter("agent_llm_calls_total", "LLM explanation calls", ["reason"])
NOTIFICATIONS = Counter("agent_notifications_total", "Slack notifications sent", ["kind"])


def beat() -> None:
    """Call at the END of every cycle."""
    HEARTBEAT.set(1)
    HEARTBEAT_TS.set(time.time())


def serve_metrics(port: int) -> None:
    start_http_server(port)
