"""Assign or propagate a request ID for correlation across logs and responses."""

from __future__ import annotations

import uuid

_ALLOWED = set("-_.")


def get_or_create_request_id(incoming: str | None) -> str:
    if incoming:
        s = incoming.strip()
        if 0 < len(s) <= 128 and all(c.isalnum() or c in _ALLOWED for c in s):
            return s
    return uuid.uuid4().hex
