"""Build the OpenAI-compatible chat request the server expects.

Pure function (no network), so it's easy to unit-test and is reused by the
smoke-test client and (later) the Day 5 gateway.
"""

from __future__ import annotations


def build_chat_payload(
    user_message: str, cfg: dict, system_prompt: str | None = None, **overrides
) -> dict:
    """Return a /v1/chat/completions body for one user message."""
    d = cfg["decoding"]
    system = system_prompt if system_prompt is not None else cfg.get("system_prompt", "")

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user_message})

    return {
        "model": "finbot",
        "messages": messages,
        "temperature": overrides.get("temperature", d["temperature"]),
        "top_p": overrides.get("top_p", d["top_p"]),
        "max_tokens": overrides.get("max_tokens", d["max_tokens"]),
    }
