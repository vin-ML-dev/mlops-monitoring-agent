"""LangGraph StateGraph wiring the agent nodes with conditional edges by cycle_type.

This is the "official" Day-7 implementation the guide describes. It reuses the
exact node functions from nodes.py (adapted to the (state)->dict LangGraph
signature by closing over ctx), so its behaviour matches pipeline.run_cycle.
"""

from __future__ import annotations

from . import nodes
from .state import AgentState


def _wrap(fn, ctx):
    def node(state):
        return fn(state, ctx)

    return node


def route_by_cycle(state) -> str:
    ct = state.get("cycle_type", "poll")
    if ct == "daily":
        return "build_daily_report"
    if ct == "canary":
        return "run_canary"
    return "correlate"


def build_graph(ctx):
    from langgraph.graph import END, StateGraph

    g = StateGraph(AgentState)
    g.add_node("fetch_metrics", _wrap(nodes.fetch_metrics, ctx))
    g.add_node("probe_services", _wrap(nodes.probe_services, ctx))
    g.add_node("detect_anomalies", _wrap(nodes.detect_anomalies, ctx))
    g.add_node("correlate", _wrap(nodes.correlate_incidents, ctx))
    g.add_node("diagnose", _wrap(nodes.diagnose, ctx))
    g.add_node("run_canary", _wrap(nodes.run_canary, ctx))
    g.add_node("build_daily_report", _wrap(nodes.build_daily_report, ctx))
    g.add_node("notify", _wrap(nodes.notify, ctx))
    g.add_node("persist", _wrap(nodes.persist, ctx))

    g.set_entry_point("fetch_metrics")
    g.add_edge("fetch_metrics", "probe_services")
    g.add_edge("probe_services", "detect_anomalies")
    g.add_conditional_edges(
        "detect_anomalies",
        route_by_cycle,
        {
            "correlate": "correlate",
            "run_canary": "run_canary",
            "build_daily_report": "build_daily_report",
        },
    )
    g.add_edge("correlate", "diagnose")
    g.add_edge("diagnose", "notify")
    g.add_edge("run_canary", "notify")
    g.add_edge("build_daily_report", "notify")
    g.add_edge("notify", "persist")
    g.add_edge("persist", END)
    return g.compile()
