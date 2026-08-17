"""Generate a Hugging Face model card (README.md) with provenance.

A good model card records: base model, what it was trained on, the data version,
the LoRA settings, and honest limitations. This is pure string-building so it is
easy to unit-test.
"""

from __future__ import annotations


def build_model_card(cfg: dict, data_version: str, gguf: bool = False) -> str:
    m = cfg["model"]
    lora = cfg["lora"]
    kind = "GGUF (llama.cpp)" if gguf else "merged fp16 (Transformers)"
    quant_line = f"- Quantization: {cfg['gguf']['quant']}\n" if gguf else ""
    return f"""---
license: apache-2.0
base_model: {m['base_id']}
tags:
- finance
- qlora
- fine-tuned
---

# finbot — {m['base_id']} fine-tuned for finance education

A small finance-education assistant fine-tuned from **{m['base_id']}** with QLoRA.
Format: {kind}.

## Training
- Base model: {m['base_id']}
- Method: QLoRA (4-bit NF4 base + LoRA adapter, r={lora['r']}, alpha={lora['alpha']})
- Data: curated `gbharti/finance-alpaca` + honesty examples (see Day 1 pipeline)
- Data version (git): `{data_version}`
{quant_line}
## Intended use
Educational explanations of finance concepts. It is trained to be honest — it
declines to predict prices, guarantee returns, or give personalized advice.

## Limitations
- Not a licensed financial advisor. Do not use for real investment decisions.
- A small (1.7B) model: it can still be wrong. Verify important facts.
- May reflect biases in the training data.
"""
