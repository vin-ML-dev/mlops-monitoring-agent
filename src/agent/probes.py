"""Active probes — is the service reachable RIGHT NOW? Distinguishes slow (probe
ok, latency high -> degraded) from unreachable (probe fails -> down).
"""

from __future__ import annotations


def _reachable(url: str, timeout: float = 5.0) -> bool:
    import requests

    try:
        r = requests.get(url, timeout=timeout)
        return r.status_code < 500
    except Exception:  # noqa: BLE001
        return False


class Probes:
    def gateway_reachable(self, gateway_base: str) -> bool:
        return _reachable(f"{gateway_base.rstrip('/')}/healthz")

    def model_reachable(self, model_base: str) -> bool:
        return _reachable(f"{model_base.rstrip('/')}/v1/models")
