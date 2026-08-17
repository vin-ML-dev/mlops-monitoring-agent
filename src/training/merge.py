"""Step 2 — MERGE.

QLoRA leaves you with a tiny adapter on top of a 4-bit base. To export the model
(push to HF, convert to GGUF) we merge the adapter into a full-precision base and
save one standalone model.

Note: we reload the base in fp16 here (NOT 4-bit) so the merged weights are clean.

Run:  python -m src.training.merge
"""

from __future__ import annotations

from . import load_train_cfg
from .model import load_tokenizer


def main() -> None:
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM

    cfg = load_train_cfg()
    base_id = cfg["model"]["base_id"]
    adapter_dir = cfg["train"]["output_dir"]
    merged_dir = cfg["merge"]["merged_dir"]

    print(f"[merge] loading base {base_id} in fp16")
    base = AutoModelForCausalLM.from_pretrained(
        base_id, torch_dtype=torch.float16, device_map="auto", trust_remote_code=True
    )
    print(f"[merge] applying adapter from {adapter_dir}")
    model = PeftModel.from_pretrained(base, adapter_dir)
    model = model.merge_and_unload()

    model.save_pretrained(merged_dir, safe_serialization=True)
    load_tokenizer(base_id).save_pretrained(merged_dir)
    print(f"[merge] merged model saved -> {merged_dir}")


if __name__ == "__main__":
    main()
