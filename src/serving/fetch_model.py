"""Download the registered GGUF from the Hub into the pod's model directory.

Runs at container startup (before the server launches). Env vars override the
config so the k8s ConfigMap/Secret can point it at a different repo/file without
rebuilding the image. Needs HF_TOKEN for a private repo.
"""

from __future__ import annotations

import os
import sys

from . import load_serve_cfg


def download() -> str:
    from huggingface_hub import hf_hub_download

    cfg = load_serve_cfg()["model"]
    repo = os.environ.get("GGUF_REPO", cfg["gguf_repo"])
    fname = os.environ.get("GGUF_FILE", cfg["gguf_file"])
    local_dir = os.environ.get("LOCAL_DIR", cfg["local_dir"])

    print(f"[fetch] {repo}/{fname} -> {local_dir}")
    path = hf_hub_download(
        repo_id=repo,
        filename=fname,
        local_dir=local_dir,
        token=os.environ.get("HF_TOKEN"),
    )
    print(f"[fetch] ready: {path}")
    return path


def main() -> int:
    try:
        download()
        return 0
    except Exception as exc:  # noqa: BLE001 - one clear message, not a traceback
        print(f"[fetch] FAILED to download the model: {exc}")
        print("[fetch] check GGUF_REPO / GGUF_FILE and that HF_TOKEN is set for a private repo.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
