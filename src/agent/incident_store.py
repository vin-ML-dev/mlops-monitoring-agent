"""Redis-backed incident state so the agent remembers across cycles.

Keys are namespaced under `agent:`. All ops fail soft — if Redis is unavailable
the agent keeps running (it just can't dedup perfectly), because a monitoring
agent must not crash when its state store hiccups.
"""

from __future__ import annotations

import json

_OPEN_KEY = "agent:open_incidents"
_NOTIFIED_KEY = "agent:last_notified"
_STATS_KEY = "agent:daily_stats"


class IncidentStore:
    def __init__(self, redis):
        self._r = redis

    def get_open_incidents(self) -> dict:
        return self._get(_OPEN_KEY, {})

    def save_open_incidents(self, incidents: dict) -> None:
        self._set(_OPEN_KEY, incidents)

    def get_last_notified(self) -> dict:
        return self._get(_NOTIFIED_KEY, {})

    def set_last_notified(self, key: str, ts: float) -> None:
        m = self.get_last_notified()
        m[key] = ts
        self._set(_NOTIFIED_KEY, m)

    def get_daily_stats(self) -> dict:
        return self._get(_STATS_KEY, {})

    def save_daily_stats(self, stats: dict) -> None:
        self._set(_STATS_KEY, stats)

    # ---- helpers (fail soft) ----
    def _get(self, key: str, default):
        try:
            raw = self._r.get(key)
            return json.loads(raw) if raw else default
        except Exception:  # noqa: BLE001
            return default

    def _set(self, key: str, value) -> None:
        import contextlib

        with contextlib.suppress(Exception):  # fail soft: state hiccup must not crash the agent
            self._r.set(key, json.dumps(value))
