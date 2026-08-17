"""Load the quantized GGUF (the served artifact) and build a generate() function.

Heavy import (llama_cpp) is inside the loader so this module imports on any
machine; only running an actual eval needs llama-cpp-python installed.
"""

from __future__ import annotations

import os


def resolve_model_path(cfg: dict) -> str:
    """Use the local GGUF if present, else download it from the Hub."""
    model = cfg["model"]
    path = model.get("gguf_path")
    if path and os.path.exists(path):
        return path

    repo = model.get("gguf_repo")
    if not repo:
        raise FileNotFoundError(
            f"GGUF not found at {path!r} and no gguf_repo configured to download."
        )
    from huggingface_hub import snapshot_download

    local_dir = snapshot_download(repo_id=repo, allow_patterns=["*.gguf"])
    ggufs = [f for f in os.listdir(local_dir) if f.endswith(".gguf")]
    if not ggufs:
        raise FileNotFoundError(f"No .gguf file found in {repo}")
    return os.path.join(local_dir, sorted(ggufs)[0])


def build_generate(cfg: dict):
    """Return a generate(prompt)->str function backed by the GGUF model."""
    from llama_cpp import Llama

    model_path = resolve_model_path(cfg)
    llm = Llama(model_path=model_path, n_ctx=cfg["model"]["n_ctx"], verbose=False)
    system_prompt = cfg["model"].get("system_prompt", "")
    d = cfg["decoding"]

    def generate(prompt: str) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        out = llm.create_chat_completion(
            messages=messages,
            max_tokens=d["max_tokens"],
            temperature=d["temperature"],
            top_p=d["top_p"],
            repeat_penalty=d["repetition_penalty"],
        )
        return out["choices"][0]["message"]["content"].strip()

    return generate
