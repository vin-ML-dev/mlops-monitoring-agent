"""Step 4 — VALIDATE.

Prove the built dataset is safe and well-formed BEFORE it can be used for
training. Two checks:
  1) schema — every record matches the chat contract (roles, non-empty content).
  2) PII leak — re-scan all text; if any PII survived scrubbing, FAIL the run.

A non-zero exit here is what lets CI block a bad dataset.

Input : data/interim/built.jsonl
Output: data/interim/validated.jsonl  (identical records, once they pass)
"""

from __future__ import annotations

import json
import sys
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from . import BUILT, VALIDATED
from .curate import _PII  # reuse the same regex patterns for the leak check


class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)


class ChatRecord(BaseModel):
    messages: list[Message]
    meta: dict


def _pii_leak(text: str) -> int:
    return sum(len(rx.findall(text)) for _, rx in _PII)


def main() -> int:
    with open(BUILT, encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh if line.strip()]

    schema_errors = 0
    leaks = 0
    validated: list[dict] = []

    for i, row in enumerate(rows):
        try:
            rec = ChatRecord(**row)
        except ValidationError as exc:
            schema_errors += 1
            print(f"[validate] schema error in record {i}: {exc.errors()[0]['msg']}")
            continue

        roles = [m.role for m in rec.messages]
        if "user" not in roles or "assistant" not in roles:
            schema_errors += 1
            print(f"[validate] record {i} missing a user or assistant turn")
            continue

        for m in rec.messages:
            leaks += _pii_leak(m.content)

        validated.append(row)

    VALIDATED.parent.mkdir(parents=True, exist_ok=True)
    with open(VALIDATED, "w", encoding="utf-8") as fh:
        for rec in validated:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(
        f"[validate] {len(validated)}/{len(rows)} passed · "
        f"schema_errors={schema_errors} · pii_leaks={leaks}"
    )

    if schema_errors > 0 or leaks > 0:
        print("[validate] FAILED — refusing to accept this dataset.")
        return 1
    print("[validate] OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
