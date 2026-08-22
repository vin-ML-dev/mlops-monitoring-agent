"""The explainer — turns deterministic findings into short plain-English text.

The LLM ONLY explains (new incidents, canary regressions, daily summaries). It
never decides up/down or pass/fail. Backends:
- "template": no external LLM — deterministic heuristic text (default; zero cost,
  air-gapped, always works). Good enough to demo Path 2 without an LLM.
- "ollama" / "openai": call a real model for richer wording.
"""

from __future__ import annotations

# heuristic root-cause hints for the template backend
_SINGLE = {
    "model_down": "the model pod is unavailable (crash, OOM, eviction, or still loading).",
    "gateway_down": "the gateway is unreachable (crashed or not ready).",
    "breaker_open": "the gateway circuit breaker opened after repeated backend failures.",
    "high_latency": "the model is slow — likely CPU saturation or heavy concurrent load.",
    "high_errors": "backend calls are failing — likely the model restarting or overloaded.",
    "restart_churn": "a pod is restarting repeatedly — likely OOM or a failing probe.",
}


def _heuristic_cause(anomalies: list[dict]) -> str:
    keys = {a["key"] for a in anomalies}
    if "high_errors" in keys and "breaker_open" in keys:
        return "backend errors tripped the circuit breaker; the model likely failed or restarted."
    if len(keys) == 1:
        return _SINGLE.get(next(iter(keys)), "a monitored condition degraded.")
    return "multiple signals degraded at once; check the model and gateway pods."


class Explainer:
    def __init__(self, cfg: dict):
        self.backend = cfg.get("llm", {}).get("backend", "template")
        self._cfg = cfg

    # ---- incident ----
    def explain_incident(self, mode: str, anomalies: list[dict], metrics: dict) -> str:
        detail = "; ".join(a["detail"] for a in anomalies)
        if self.backend == "template":
            return f"{mode.upper()}: {detail}. Likely cause: {_heuristic_cause(anomalies)}"
        prompt = (
            f"Serving mode: {mode}. Anomalies: {detail}. Metrics: {metrics}. "
            "In 2 short sentences, explain what happened and the most likely why. "
            "Do not suggest fixes; this is an explanation only."
        )
        return self._call_llm(prompt) or f"{mode.upper()}: {detail}."

    # ---- canary regression ----
    def explain_canary(self, failures: list[dict]) -> str:
        detail = "; ".join(f"{f['name']}: {f['reason']}" for f in failures)
        if self.backend == "template":
            return f"Quality canary regressed — {detail}. The model is up but its answers changed."
        prompt = (
            f"A deterministic quality canary failed: {detail}. "
            "In 2 short sentences, explain the likely regression. Explanation only, no fixes."
        )
        return self._call_llm(prompt) or f"Canary regressed — {detail}."

    # ---- daily summary ----
    def summarize_daily(self, stats: dict) -> str:
        line = ", ".join(f"{k}={v}" for k, v in stats.items())
        if self.backend == "template":
            return f"Daily summary — {line}."
        prompt = (
            f"Summarize this platform's day for a Slack report in 3-4 sentences: {stats}. "
            "Be factual; do not invent numbers."
        )
        return self._call_llm(prompt) or f"Daily summary — {line}."

    # ---- backends ----
    def _call_llm(self, prompt: str) -> str | None:
        try:
            if self.backend == "ollama":
                return self._ollama(prompt)
            if self.backend == "openai":
                return self._openai(prompt)
        except Exception:  # noqa: BLE001 - explanation is best-effort; never crash the agent
            return None
        return None

    def _ollama(self, prompt: str) -> str:
        import requests

        o = self._cfg["llm"]["ollama"]
        r = requests.post(
            f"{o['base_url'].rstrip('/')}/api/generate",
            json={"model": o["model"], "prompt": prompt, "stream": False},
            timeout=60,
        )
        r.raise_for_status()
        return r.json().get("response", "").strip()

    def _openai(self, prompt: str) -> str:
        import os

        import requests

        o = self._cfg["llm"]["openai"]
        r = requests.post(
            f"{o.get('base_url', 'https://api.openai.com/v1').rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {os.environ.get('OPENAI_API_KEY', '')}"},
            json={"model": o["model"], "messages": [{"role": "user", "content": prompt}]},
            timeout=60,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
