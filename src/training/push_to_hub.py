"""Step 3 — PUSH MODEL TO HUB.

Upload the merged fp16 model, its tokenizer, and a model card to Hugging Face.
Needs `HF_TOKEN` in the environment (or `huggingface-cli login`).

Run:  python -m src.training.push_to_hub
"""

from __future__ import annotations

from pathlib import Path

from . import load_train_cfg
from .mlflow_utils import data_version
from .model_card import build_model_card


def main() -> None:
    from huggingface_hub import HfApi
    from transformers import AutoModelForCausalLM, AutoTokenizer

    cfg = load_train_cfg()
    merged_dir = cfg["merge"]["merged_dir"]
    repo_id = cfg["hub"]["repo_id"]
    private = cfg["hub"].get("private", True)

    # write the model card into the merged dir
    card = build_model_card(cfg, data_version(), gguf=False)
    Path(merged_dir, "README.md").write_text(card, encoding="utf-8")

    print(f"[push] uploading merged model -> {repo_id} (private={private})")
    model = AutoModelForCausalLM.from_pretrained(merged_dir)
    tok = AutoTokenizer.from_pretrained(merged_dir)
    model.push_to_hub(repo_id, private=private)
    tok.push_to_hub(repo_id, private=private)

    # upload the card explicitly (so it shows on the repo page)
    HfApi().upload_file(
        path_or_fileobj=str(Path(merged_dir, "README.md")),
        path_in_repo="README.md",
        repo_id=repo_id,
        repo_type="model",
    )
    print(f"[push] done: https://huggingface.co/{repo_id}")


if __name__ == "__main__":
    main()
