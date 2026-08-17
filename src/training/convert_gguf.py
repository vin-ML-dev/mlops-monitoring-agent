"""Step 4 — GGUF CONVERT + QUANTIZE + PUSH.

Convert the merged fp16 model to GGUF (llama.cpp's format), quantize it (default
Q4_K_M), and upload the .gguf to Hugging Face. This is CPU work — but it's handy
to run in the same GPU session so you only rent the GPU once.

Assumes llama.cpp is available at cfg['gguf']['llama_cpp_dir'] (the notebook
clones + builds it). Needs `HF_TOKEN` to push.

Run:  python -m src.training.convert_gguf
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from . import load_train_cfg
from .mlflow_utils import data_version
from .model_card import build_model_card


def _run(cmd: list[str]) -> None:
    print("[gguf] $", " ".join(cmd))
    subprocess.run(cmd, check=True)


def main() -> None:
    from huggingface_hub import HfApi

    cfg = load_train_cfg()
    merged_dir = cfg["merge"]["merged_dir"]
    llama_dir = Path(cfg["gguf"]["llama_cpp_dir"])
    quant = cfg["gguf"]["quant"]
    prefix = cfg["gguf"]["outfile_prefix"]
    gguf_repo = cfg["hub"]["gguf_repo_id"]
    private = cfg["hub"].get("private", True)

    f16_path = f"{prefix}-f16.gguf"
    quant_path = f"{prefix}-{quant}.gguf"

    # 1) HF model -> GGUF (f16)
    _run(
        [
            "python",
            str(llama_dir / "convert_hf_to_gguf.py"),
            merged_dir,
            "--outfile",
            f16_path,
            "--outtype",
            "f16",
        ]
    )
    # 2) quantize
    _run([str(llama_dir / "llama-quantize"), f16_path, quant_path, quant])

    # 3) push the quantized GGUF + a card
    api = HfApi()
    api.create_repo(gguf_repo, private=private, exist_ok=True)
    card = build_model_card(cfg, data_version(), gguf=True)
    Path("README_gguf.md").write_text(card, encoding="utf-8")
    api.upload_file(
        path_or_fileobj="README_gguf.md",
        path_in_repo="README.md",
        repo_id=gguf_repo,
        repo_type="model",
    )
    api.upload_file(
        path_or_fileobj=quant_path,
        path_in_repo=Path(quant_path).name,
        repo_id=gguf_repo,
        repo_type="model",
    )
    print(f"[gguf] pushed {Path(quant_path).name} -> https://huggingface.co/{gguf_repo}")
    print("[gguf] this .gguf is what llama.cpp loads in-cluster on Day 4")


if __name__ == "__main__":
    main()
