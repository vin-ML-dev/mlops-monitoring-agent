"""Load the base model in 4-bit (QLoRA) and attach the LoRA adapter.

All heavy imports are inside functions so this file imports on any machine.
"""

from __future__ import annotations


def load_tokenizer(base_id: str):
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained(base_id, trust_remote_code=True)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token  # needed for batching
    return tok


def load_base_4bit(base_id: str, quant_cfg: dict):
    """Load the base model quantized to 4-bit NF4 (fits a small GPU)."""
    import torch
    from transformers import AutoModelForCausalLM, BitsAndBytesConfig

    compute_dtype = getattr(torch, quant_cfg.get("bnb_4bit_compute_dtype", "bfloat16"))
    bnb = BitsAndBytesConfig(
        load_in_4bit=quant_cfg.get("load_in_4bit", True),
        bnb_4bit_quant_type=quant_cfg.get("bnb_4bit_quant_type", "nf4"),
        bnb_4bit_compute_dtype=compute_dtype,
        bnb_4bit_use_double_quant=quant_cfg.get("bnb_4bit_use_double_quant", True),
    )
    model = AutoModelForCausalLM.from_pretrained(
        base_id,
        quantization_config=bnb,
        device_map="auto",
        trust_remote_code=True,
    )
    model.config.use_cache = False  # required with gradient checkpointing
    return model


def build_lora_config(lora_cfg: dict):
    from peft import LoraConfig

    return LoraConfig(
        r=lora_cfg["r"],
        lora_alpha=lora_cfg["alpha"],
        lora_dropout=lora_cfg["dropout"],
        target_modules=lora_cfg["target_modules"],
        bias="none",
        task_type="CAUSAL_LM",
    )
