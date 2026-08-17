"""Register an APPROVED model version (semver) with full provenance.

Only registers if the evaluation gate passed (unless --force). Appends an entry
to a simple JSON registry: version, timestamp, git sha, data version, model
source, and the eval scores it passed with. This is the record that says
"this exact model, from this exact data, cleared the gate."

Usage:  python -m src.evaluation.register --version v1.0.0
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime

from . import ROOT, load_eval_cfg
from .gate import check


def _git(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], stderr=subprocess.DEVNULL).decode().strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def data_version() -> str:
    tag = _git("describe", "--tags", "--exact-match")
    return tag if tag != "unknown" else _git("rev-parse", "--short", "HEAD")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True, help="semver, e.g. v1.0.0")
    ap.add_argument("--force", action="store_true", help="register even if the gate failed")
    args = ap.parse_args()

    cfg = load_eval_cfg()
    report_path = ROOT / cfg["report_path"]
    if not report_path.exists():
        print(f"[register] no report at {cfg['report_path']} — run `make gate` first.")
        return 1

    report = json.loads(report_path.read_text())
    passed, reasons = check(report["summary"], cfg["thresholds"])
    if not passed and not args.force:
        print("[register] REFUSED — the model did not pass the gate:")
        print("[register]   " + "\n[register]   ".join(reasons))
        print("[register] (use --force only if you know what you're doing)")
        return 1

    registry_path = ROOT / cfg["registry_path"]
    registry = json.loads(registry_path.read_text()) if registry_path.exists() else []

    entry = {
        "version": args.version,
        "registered_at": datetime.now(UTC).isoformat(),
        "git_sha": _git("rev-parse", "--short", "HEAD"),
        "data_version": data_version(),
        "model_gguf": cfg["model"].get("gguf_repo") or cfg["model"].get("gguf_path"),
        "gate_passed": passed,
        "forced": bool(args.force and not passed),
        "scores": report["summary"],
    }
    registry.append(entry)
    registry_path.write_text(json.dumps(registry, indent=2))

    print(f"[register] recorded {args.version} -> {cfg['registry_path']}")
    print(
        f"[register] tag it in git with:  git tag -a {args.version} "
        f"-m 'model {args.version} (passed gate)'  &&  git push origin {args.version}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
