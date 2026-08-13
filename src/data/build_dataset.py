# ruff: noqa: E501  (honesty example strings are intentionally long)
"""Step 3 — BUILD DATASET.

Turn cleaned records into the chat format a chat model is fine-tuned on:
  {"messages": [{"role": "system"...}, {"role": "user"...}, {"role": "assistant"...}],
   "meta": {...}}

Also inject a few curated HONESTY examples. We deliberately filtered out low-
quality refusals earlier — but we *add back* good "I can't guarantee that / I'm
not a licensed advisor" replies so the finance bot learns to be honest instead
of hallucinating predictions. Bad refusals out, good honesty in.

Input : data/interim/curated.jsonl
Output: data/interim/built.jsonl
"""

from __future__ import annotations

import json

from . import BUILT, CURATED, load_data_cfg

# Finance-flavored honesty examples (don't predict prices, don't guarantee returns).
HONESTY_EXAMPLES: list[dict] = [
    {
        "instruction": "Which stock will double next month? Just tell me.",
        "response": "I can't predict specific stock movements, and anyone who guarantees that isn't being honest with you. I can explain how to evaluate a company's fundamentals so you can make your own informed decision.",
        "intent": "honesty_no_prediction",
    },
    {
        "instruction": "Guarantee me a 20% return this year.",
        "response": "No one can guarantee investment returns — higher expected returns always come with higher risk. I can walk you through how risk and return relate and how diversification helps.",
        "intent": "honesty_no_guarantee",
    },
    {
        "instruction": "Should I put all my savings into this one crypto coin?",
        "response": "I'm not a licensed financial advisor, so I can't tell you what to do with your money. Concentrating everything in one volatile asset is generally very risky; I can explain diversification and position sizing so you can decide.",
        "intent": "honesty_not_advisor",
    },
    {
        "instruction": "What will the S&P 500 close at on December 31st?",
        "response": "I don't know future market levels — they can't be predicted reliably. I can explain what tends to drive market movements over the long term instead.",
        "intent": "honesty_unknown",
    },
    {
        "instruction": "Is it a good time to buy? Yes or no.",
        "response": "I can't give you a personalized buy/sell call — that depends on your goals, timeline, and risk tolerance, and I'm not a licensed advisor. I can help you think through those factors.",
        "intent": "honesty_no_personal_advice",
    },
]


def to_chat(rec: dict, system_prompt: str | None, kind: str) -> dict:
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": rec["instruction"]})
    messages.append({"role": "assistant", "content": rec["response"]})
    return {
        "messages": messages,
        "meta": {"kind": kind, "id": rec.get("id"), "intent": rec.get("intent")},
    }


def main() -> None:
    cfg = load_data_cfg()
    system_prompt = cfg["build"].get("system_prompt")

    with open(CURATED, encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh if line.strip()]

    out = [to_chat(r, system_prompt, kind="finance") for r in rows]

    if cfg["build"].get("add_honesty_examples"):
        for i, h in enumerate(HONESTY_EXAMPLES):
            h = {**h, "id": f"honesty-{i}"}
            out.append(to_chat(h, system_prompt, kind="honesty"))

    BUILT.parent.mkdir(parents=True, exist_ok=True)
    with open(BUILT, "w", encoding="utf-8") as fh:
        for rec in out:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    n_honesty = sum(1 for r in out if r["meta"]["kind"] == "honesty")
    print(f"[build] wrote {len(out)} chat records ({n_honesty} honesty) -> {BUILT}")


if __name__ == "__main__":
    main()
