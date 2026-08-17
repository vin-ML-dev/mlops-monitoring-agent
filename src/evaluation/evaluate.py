"""Run every golden item through the model, score it, and write eval_report.json.

`run_eval` takes a `generate` callable so it's testable without a real model
(tests pass a fake generate). The CLI wires up the real GGUF runner.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from . import ROOT, load_eval_cfg
from .metrics import aggregate, score_item


def load_golden(path) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def run_eval(generate, golden: list[dict], cfg: dict) -> dict:
    """Score the whole golden set with the given generate() function."""
    results = []
    for item in golden:
        response = generate(item["instruction"])
        results.append(score_item(item, response, cfg))
    summary = aggregate(results)
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "summary": summary,
        "results": results,
    }


def write_report(report: dict, path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)


def main() -> None:
    cfg = load_eval_cfg()
    golden = load_golden(ROOT / cfg["golden_path"])

    from .gguf_runner import build_generate

    generate = build_generate(cfg)
    report = run_eval(generate, golden, cfg)
    write_report(report, ROOT / cfg["report_path"])

    s = report["summary"]
    print(
        f"[eval] {s['passed']}/{s['total']} passed "
        f"· overall={s['overall_pass_rate']} · honesty={s['honesty_pass_rate']} "
        f"· concept={s['concept_pass_rate']}"
    )
    print(f"[eval] report -> {cfg['report_path']}")


if __name__ == "__main__":
    main()
