"""Step 1 — TRAIN.

Fine-tune Qwen3-1.7B with QLoRA using TRL's SFTTrainer, track with MLflow, and
save the adapter. Checkpoints are written often and training auto-RESUMES from
the last checkpoint — so a Colab disconnect costs you minutes, not hours.

Run (on a GPU):  python -m src.training.train
"""

from __future__ import annotations

import os

from . import load_train_cfg
from .data import build_hf_dataset
from .mlflow_utils import log_adapter, start_run
from .model import build_lora_config, load_base_4bit, load_tokenizer


def _has_checkpoint(output_dir: str) -> bool:
    return os.path.isdir(output_dir) and any(
        d.startswith("checkpoint-") for d in os.listdir(output_dir)
    )


def main() -> None:
    from trl import SFTConfig, SFTTrainer

    cfg = load_train_cfg()
    t = cfg["train"]

    tokenizer = load_tokenizer(cfg["model"]["base_id"])
    train_ds = build_hf_dataset(cfg["data"]["train_path"], tokenizer)
    print(f"[train] {len(train_ds)} training examples")

    model = load_base_4bit(cfg["model"]["base_id"], cfg["quant"])
    peft_config = build_lora_config(cfg["lora"])

    sft_config = SFTConfig(
        output_dir=t["output_dir"],
        num_train_epochs=t["epochs"],
        per_device_train_batch_size=t["per_device_batch_size"],
        gradient_accumulation_steps=t["grad_accum"],
        learning_rate=t["lr"],
        warmup_ratio=t["warmup_ratio"],
        logging_steps=t["logging_steps"],
        save_steps=t["save_steps"],
        save_total_limit=t["save_total_limit"],
        seed=t["seed"],
        bf16=t["bf16"],
        gradient_checkpointing=t["gradient_checkpointing"],
        max_seq_length=cfg["model"]["max_seq_len"],
        dataset_text_field="text",
        report_to="mlflow",
    )

    trainer = SFTTrainer(
        model=model,
        args=sft_config,
        train_dataset=train_ds,
        peft_config=peft_config,
        processing_class=tokenizer,
    )

    with start_run(cfg):
        resume = _has_checkpoint(t["output_dir"])
        if resume:
            print("[train] resuming from last checkpoint")
        trainer.train(resume_from_checkpoint=resume)
        trainer.save_model(t["output_dir"])  # saves the adapter
        tokenizer.save_pretrained(t["output_dir"])
        log_adapter(t["output_dir"])

    print(f"[train] adapter saved -> {t['output_dir']}")


if __name__ == "__main__":
    main()
