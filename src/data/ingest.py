"""Step 1 — INGEST.

Stream raw finance instruction examples from the  finance-alpaca
dataset on Hugging Face. Needs internet. If the stream fails, we print a clear
message and stop — no silent fallback.

Output: data/interim/ingested.jsonl  (one raw record per line)

A raw record looks like:
  {"id", "instruction", "input", "output"}
There is NO category column (that's why Day 1's split is random).
"""

from __future__ import annotations

import json
import sys

from . import INGESTED, load_params


def stream_finance_alpaca(name: str, n: int) -> list[dict]:
    """Stream up to n rows from finance-alpaca on Hugging Face."""
    from datasets import load_dataset

    ds = load_dataset(name, split="train", streaming=True)
    rows: list[dict] = []
    for i, row in enumerate(ds):
        if i >= n:
            break
        rows.append(
            {
                "id": f"fin-{i}",
                "instruction": (row.get("instruction") or "").strip(),
                "input": (row.get("input") or "").strip(),
                "output": (row.get("output") or "").strip(),
            }
        )
    return rows


def main() -> int:
    params = load_params()
    INGESTED.parent.mkdir(parents=True, exist_ok=True)

    hf_dataset = params["ingest"]["hf_dataset"]
    n = params["ingest"]["sample_size"]

    try:
        rows = stream_finance_alpaca(hf_dataset, n)
    except Exception as exc:  # noqa: BLE001 - we want one clean, polite message
        print(
            f"[ingest] Could not reach Hugging Face to stream '{hf_dataset}'.\n"
            f"[ingest] Reason: {exc}\n"
            f"[ingest] Check your internet connection and try again."
        )
        return 1

    print(f"[ingest] streamed {len(rows)} rows from Hugging Face")

    with open(INGESTED, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"[ingest] wrote {len(rows)} rows -> {INGESTED}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
