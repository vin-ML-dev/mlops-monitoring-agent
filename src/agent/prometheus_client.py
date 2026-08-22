"""Query Prometheus with a FIXED set of PromQL (never LLM-generated).

Returns the same signals the Day-6 rules use, so detection stays aligned.
"""

from __future__ import annotations


class PromQL:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def query(self, expr: str) -> float | None:
        """Instant query -> scalar float, or None if no data / error."""
        import requests

        try:
            r = requests.get(f"{self.base_url}/api/v1/query", params={"query": expr}, timeout=10)
            r.raise_for_status()
            result = r.json()["data"]["result"]
            if not result:
                return None
            return float(result[0]["value"][1])
        except Exception:  # noqa: BLE001 - a missing signal is None, not a crash
            return None

    def collect(self) -> dict:
        """The fixed signal set (mirrors Day-6 metrics)."""
        return {
            "p95_latency": self.query(
                "histogram_quantile(0.95, sum(rate("
                "gateway_http_request_duration_seconds_bucket[5m])) by (le))"
            ),
            "error_ratio": self.query(
                'sum(rate(gateway_backend_requests_total{outcome="error"}[5m])) / '
                "clamp_min(sum(rate(gateway_backend_requests_total[5m])), 1e-9)"
            ),
            "breaker_state": self.query("max(gateway_circuit_breaker_state)"),
            "model_replicas": self.query(
                "kube_deployment_status_replicas_available"
                '{namespace="finbot",deployment="finbot-model"}'
            ),
            "pod_restarts": self.query(
                'increase(kube_pod_container_status_restarts_total{namespace="finbot"}[15m])'
            ),
            "request_rate": self.query("sum(rate(gateway_http_requests_total[5m]))"),
            "cache_hit_ratio": self.query(
                'sum(rate(gateway_cache_requests_total{result="hit"}[5m])) / '
                "clamp_min(sum(rate(gateway_cache_requests_total[5m])), 1e-9)"
            ),
        }
