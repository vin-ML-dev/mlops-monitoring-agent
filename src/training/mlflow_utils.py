"""MLflow tracking helpers: log params, metrics, and — importantly — the exact
DATA VERSION each run trained on, so every model is traceable back to its data.
"""

from __future__ import annotations

import subprocess


def data_version() -> str:
    """Best-effort provenance for the data this run trains on.

    Order of preference:
      1. An exact git TAG on the current commit (e.g. "data-v1") — most readable.
      2. The short git commit hash (e.g. "a1b2c3d") — always works if in a repo.
      3. "unknown" — outside a git repo / git unavailable.

    Tagging your data (`git tag -a data-v1 -m "..."`) makes model cards say
    "Data version: data-v1" instead of a cryptic hash — while still falling back
    gracefully before you've tagged anything.
    """
    # 1) exact tag on this commit, if there is one
    try:
        tag = (
            subprocess.check_output(
                ["git", "describe", "--tags", "--exact-match"],
                stderr=subprocess.DEVNULL,
            )
            .decode()
            .strip()
        )
        if tag:
            return tag
    except Exception:  # noqa: BLE001 - no exact tag on this commit; fall through
        pass

    # 2) short commit hash
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"]).decode().strip()
    except Exception:  # noqa: BLE001 - not a git repo / git missing
        return "unknown"


def start_run(cfg: dict, experiment: str = "finbot-qlora"):
    """Start an MLflow run and log the config + data version. Returns the run
    context manager so the caller can `with start_run(...) as run:`."""
    import mlflow

    mlflow.set_experiment(experiment)
    run = mlflow.start_run()
    mlflow.log_params(
        {
            "base_model": cfg["model"]["base_id"],
            "lora_r": cfg["lora"]["r"],
            "lora_alpha": cfg["lora"]["alpha"],
            "lr": cfg["train"]["lr"],
            "epochs": cfg["train"]["epochs"],
            "eff_batch": cfg["train"]["per_device_batch_size"] * cfg["train"]["grad_accum"],
            "max_seq_len": cfg["model"]["max_seq_len"],
            "data_version": data_version(),
        }
    )
    return run


def log_adapter(adapter_dir: str) -> None:
    import mlflow

    mlflow.log_artifacts(adapter_dir, artifact_path="qlora-adapter")
