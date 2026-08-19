"""API-key authentication with a constant-time comparison (avoids timing attacks).

The key never appears in source, logs, errors, or metrics labels.
"""

from __future__ import annotations

import hmac


def extract_bearer(header_value: str | None) -> str | None:
    if not header_value:
        return None
    v = header_value.strip()
    if v.lower().startswith("bearer "):
        return v[7:].strip()
    return v


def verify_api_key(header_value: str | None, expected: str) -> bool:
    token = extract_bearer(header_value)
    if not token or not expected:
        return False
    return hmac.compare_digest(token, expected)
