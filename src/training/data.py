"""Load the Day 1 chat data and prepare it for fine-tuning.

Day 1 produced records like:
  {"messages": [{"role": "system"...}, {"role": "user"...}, {"role": "assistant"...}],
   "meta": {...}}

For SFT we turn each record into a single training string using the model's
*chat template* (so the model sees data in exactly the format it expects).
"""

from __future__ import annotations

import json

VALID_ROLES = {"system", "user", "assistant"}


def load_chat_jsonl(path) -> list[dict]:
    """Read a JSONL file of chat records into a list of dicts."""
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def is_valid_record(rec: dict) -> bool:
    """A record must have a non-empty messages list with valid roles, and at
    least one user turn and one assistant turn."""
    msgs = rec.get("messages")
    if not isinstance(msgs, list) or not msgs:
        return False
    roles = []
    for m in msgs:
        if m.get("role") not in VALID_ROLES or not str(m.get("content", "")).strip():
            return False
        roles.append(m["role"])
    return "user" in roles and "assistant" in roles


def render_chatml(messages: list[dict]) -> str:
    """A simple ChatML rendering used as a FALLBACK (and in tests) when no
    tokenizer is available. The real training path uses the model's own
    chat template (see format_with_tokenizer)."""
    parts = []
    for m in messages:
        parts.append(f"<|im_start|>{m['role']}\n{m['content']}<|im_end|>")
    return "\n".join(parts) + "\n"


def format_with_tokenizer(messages: list[dict], tokenizer) -> str:
    """Apply the model's real chat template to a list of messages."""
    return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)


def build_hf_dataset(path, tokenizer=None):
    """Load JSONL -> filter invalid -> HF Dataset with a 'text' column ready for SFT."""
    from datasets import Dataset

    records = [r for r in load_chat_jsonl(path) if is_valid_record(r)]
    if tokenizer is not None:
        texts = [format_with_tokenizer(r["messages"], tokenizer) for r in records]
    else:
        texts = [render_chatml(r["messages"]) for r in records]
    return Dataset.from_dict({"text": texts})
