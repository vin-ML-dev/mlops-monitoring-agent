"""Correlation — decide which anomalies are new, still-open, or recovered, and
which to notify (respecting a per-incident cooldown).

Pure function. This is what stops the agent from re-explaining the same 30-minute
outage on every 60-second poll.
"""

from __future__ import annotations


def correlate(
    anomalies: list[dict],
    open_incidents: dict,
    now: float,
    cooldown_seconds: float,
    last_notified: dict,
) -> dict:
    """Return {new, still_open, recovered, to_notify}.

    - new: anomaly not previously open -> always notify (LLM explains).
    - still_open: anomaly already open -> notify only if cooldown elapsed.
    - recovered: previously open but no longer present -> notify recovery.
    """
    current = {a["key"]: a for a in anomalies}
    open_keys = set(open_incidents.keys())
    current_keys = set(current.keys())

    new_keys = current_keys - open_keys
    still_keys = current_keys & open_keys
    recovered_keys = open_keys - current_keys

    to_notify: list[dict] = []
    for key, a in current.items():
        if key in new_keys:
            to_notify.append(a)
        elif key in still_keys:
            last = last_notified.get(key, 0)
            if now - last >= cooldown_seconds:
                to_notify.append(a)

    return {
        "new": [current[k] for k in new_keys],
        "still_open": [current[k] for k in still_keys],
        "recovered": sorted(recovered_keys),
        "to_notify": to_notify,
    }
