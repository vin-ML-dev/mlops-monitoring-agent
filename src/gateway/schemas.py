"""Public request/response schemas + config-driven limit enforcement.

Validation is a security control: reject impossible/oversized requests before they
consume inference capacity. Basic ranges live in the model; config-driven caps
(max messages, message length, max_tokens cap) are enforced by enforce_limits().
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .errors import ValidationFailed


class Message(BaseModel):
    role: str
    content: str


class GenerateRequest(BaseModel):
    messages: list[Message] = Field(min_length=1)
    max_tokens: int = Field(default=128, gt=0)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    top_p: float = Field(default=1.0, ge=0.0, le=1.0)
    stream: bool = False


class GenerateResponse(BaseModel):
    request_id: str
    model: str
    content: str
    cached: bool
    usage: dict | None = None


def enforce_limits(req: GenerateRequest, cfg: dict) -> None:
    """Config-driven caps. Raises ValidationFailed on violation."""
    v = cfg["validation"]
    if len(req.messages) > v["max_messages"]:
        raise ValidationFailed(f"Too many messages (max {v['max_messages']}).")
    for m in req.messages:
        if len(m.content) > v["max_message_chars"]:
            raise ValidationFailed(f"A message exceeds {v['max_message_chars']} characters.")
    if req.max_tokens > v["max_tokens_cap"]:
        raise ValidationFailed(f"max_tokens exceeds cap ({v['max_tokens_cap']}).")


def to_model_payload(req: GenerateRequest, model_name: str = "finbot") -> dict:
    """Translate the public request into the model's OpenAI-shaped body."""
    return {
        "model": model_name,
        "messages": [m.model_dump() for m in req.messages],
        "max_tokens": req.max_tokens,
        "temperature": req.temperature,
        "top_p": req.top_p,
        "stream": req.stream,
    }
