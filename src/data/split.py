"""Step 5 — SPLIT.

Split the validated dataset into train / test / validation by FIXED COUNTS set
in params.yaml (default 5000 / 1000 / 1000).

Default is a RANDOM split (the production-safe choice — needs no label column;
finance-alpaca has none). If configs/data.yaml sets `split.stratify_by`, we
stratify on that field (auto-falls back to random if it's missing).

If the available pool is smaller than the requested total (e.g. the tiny offline
sample), we scale the counts down proportionally so it still runs.

The split is deterministic (fixed seed) so it is reproducible.

Input : data/interim/validated.jsonl
Output: data/processed/{train,val,test}.jsonl
"""

from __future__ import annotations

import json
import random
from collections import defaultdict

from . import TEST, TRAIN, VAL, VALIDATED, load_data_cfg, load_params


def _resolve_counts(pool: int, n_train: int, n_val: int, n_test: int) -> tuple[int, int, int]:
    """Return counts that fit the pool; scale down proportionally if pool is small."""
    total = n_train + n_val + n_test
    if pool >= total:
        return n_train, n_val, n_test
    frac = pool / total
    t = int(n_train * frac)
    v = int(n_val * frac)
    return t, v, pool - t - v  # test gets the remainder


def main() -> None:
    params = load_params()
    cfg = load_data_cfg()
    seed = params["seed"]
    req_train = params["split"]["train"]
    req_val = params["split"]["val"]
    req_test = params["split"]["test"]
    stratify_by = cfg["split"].get("stratify_by")

    with open(VALIDATED, encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh if line.strip()]

    rng = random.Random(seed)
    n_train, n_val, n_test = _resolve_counts(len(rows), req_train, req_val, req_test)

    can_stratify = bool(stratify_by) and all(
        r.get("meta", {}).get(stratify_by) is not None for r in rows
    )
    if stratify_by and not can_stratify:
        print(f"[split] '{stratify_by}' missing on some rows -> falling back to RANDOM split")

    if can_stratify:
        groups: dict[str, list] = defaultdict(list)
        for r in rows:
            groups[str(r["meta"][stratify_by])].append(r)
        train: list = []
        val: list = []
        test: list = []
        total = len(rows)
        for _key, items in groups.items():
            rng.shuffle(items)
            share = len(items) / total
            gt, gv = int(n_train * share), int(n_val * share)
            train += items[:gt]
            val += items[gt : gt + gv]
            test += items[gt + gv : gt + gv + int(n_test * share)]
        mode = f"stratified by '{stratify_by}'"
    else:
        rng.shuffle(rows)
        train = rows[:n_train]
        val = rows[n_train : n_train + n_val]
        test = rows[n_train + n_val : n_train + n_val + n_test]
        mode = "random"

    for part in (train, val, test):
        rng.shuffle(part)

    TRAIN.parent.mkdir(parents=True, exist_ok=True)
    for path, part in ((TRAIN, train), (VAL, val), (TEST, test)):
        with open(path, "w", encoding="utf-8") as fh:
            for rec in part:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(
        f"[split] {mode} · pool={len(rows)} -> "
        f"train={len(train)} val={len(val)} test={len(test)}"
    )


if __name__ == "__main__":
    main()
