"""The GATE — the thing that blocks a bad model.

Applies the thresholds from eval.yaml to an evaluation summary and exits
non-zero on failure, so CI (or `make gate`) refuses to promote a model that
doesn't clear the bar. Honesty (safety) has a higher bar than general accuracy.
"""

from __future__ import annotations

import sys

from . import ROOT, load_eval_cfg


def check(summary: dict, thresholds: dict) -> tuple[bool, list[str]]:
    """Return (passed, reasons). A missing honesty set doesn't block."""
    reasons = []

    overall = summary.get("overall_pass_rate") or 0.0
    min_overall = thresholds["min_overall_pass_rate"]
    overall_ok = overall >= min_overall
    reasons.append(f"{'OK ' if overall_ok else 'FAIL'} overall {overall:.2f} >= {min_overall:.2f}")

    honesty = summary.get("honesty_pass_rate")
    min_honesty = thresholds["min_honesty_pass_rate"]
    if honesty is None:
        honesty_ok = True
        reasons.append("SKIP honesty (no honesty items in golden set)")
    else:
        honesty_ok = honesty >= min_honesty
        reasons.append(
            f"{'OK ' if honesty_ok else 'FAIL'} honesty {honesty:.2f} >= {min_honesty:.2f} "
            f"(safety-critical)"
        )

    return (overall_ok and honesty_ok), reasons


def main() -> int:
    cfg = load_eval_cfg()

    # run a fresh evaluation (build the model + score the golden set)
    from .evaluate import load_golden, run_eval, write_report
    from .gguf_runner import build_generate

    golden = load_golden(ROOT / cfg["golden_path"])
    generate = build_generate(cfg)
    report = run_eval(generate, golden, cfg)
    write_report(report, ROOT / cfg["report_path"])

    passed, reasons = check(report["summary"], cfg["thresholds"])
    print("[gate] " + "\n[gate] ".join(reasons))
    if passed:
        print("[gate] PASS — model may be registered/deployed.")
        return 0
    print("[gate] FAIL — model is blocked. Fix data/model and re-run.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
