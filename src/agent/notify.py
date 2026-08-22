"""Slack notifier — Path 2 (agent explanation). Deliberately DISTINCT from the
Alertmanager message so the two paths are recognisable. Best-effort: a Slack
failure must not crash the agent.
"""

from __future__ import annotations


class SlackNotifier:
    def __init__(self, webhook: str | None):
        self.webhook = webhook

    def _send(self, title: str, text: str, color: str) -> bool:
        if not self.webhook:
            return False
        import requests

        try:
            r = requests.post(
                self.webhook,
                json={
                    "attachments": [
                        {
                            "color": color,
                            "title": title,
                            "text": text,
                            "footer": "finbot monitoring agent · Path 2",
                        }
                    ]
                },
                timeout=10,
            )
            return r.status_code < 300
        except Exception:  # noqa: BLE001
            return False

    def notify_incident(self, key: str, mode: str, explanation: str) -> bool:
        icon = "🔻" if mode == "down" else "⚠️"
        return self._send(f"{icon} [AGENT] {mode.upper()} · {key}", explanation, "danger")

    def notify_recovery(self, key: str, text: str) -> bool:
        return self._send(f"✅ [AGENT] recovered · {key}", text, "good")

    def notify_canary(self, explanation: str) -> bool:
        return self._send("🧪 [AGENT] quality canary regression", explanation, "warning")

    def notify_daily(self, summary: str) -> bool:
        return self._send("📊 [AGENT] daily summary", summary, "#3AA3E3")
