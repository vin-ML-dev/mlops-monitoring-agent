"""Step 2b — CURATE.

Apply the six quality filters, then scrub PII from every kept record. Write the
cleaned records plus a human-readable curation_report.json (the audit trail).

finance-alpaca is Alpaca-format, so we build the user text from
`instruction` (+ optional `input`) and treat `output` as the response.

PII scrubbing = regex backstop (always on) + optional Presidio NER layer,
restricted to SENSITIVE entities only (email, phone, card, SSN). We do NOT
scrub LOCATION, DATE_TIME, or NRP (nationality/religion) — those are
legitimate answer content ("Tokyo", "3 hours", "Japanese" are not PII).
Scrubbing them replaces real words with placeholders that leak into training
answers and teach the model to emit "<LOCATION>" instead of an actual place
(see INC-013). No single detector is perfect, so the regex layer ALWAYS runs,
and if Presidio is unavailable we fall back to regex — visibly, not silently.

Input : data/interim/ingested.jsonl
Output: data/interim/curated.jsonl , data/interim/curation_report.json
"""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, datetime

from . import CURATED, INGESTED, REPORT, load_data_cfg
from .quality_filters import (
    bad_length,
    is_echo,
    is_refusal,
    is_repetitive,
    is_truncated,
    wrong_language,
)

# --------------------------------------------------------------------- PII
# Regex backstop — ALWAYS runs, regardless of whether Presidio is enabled.
# Structured, sensitive identifiers only: email, card, SSN, phone, IP, Aadhaar.
# Order matters: greedy-digit types (card, Aadhaar, SSN) before phone, so a
# phone pattern can't nibble digits out of a longer number.
#PHONE = re.compile(r"(?:\+?\d{1,3}[\s-])?(?:\(?\d{3,5}\)?[\s-])\d{3}[\s-]\d{4}\b")

_PII: list[tuple[str, re.Pattern]] = [
    ("EMAIL", re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")),
    ("CREDIT_CARD", re.compile(r"\b(?:\d[ -]*?){13,16}\b")),
    ("AADHAAR", re.compile(r"\b\d{4}\s\d{4}\s\d{4}\b")),
    ("US_SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("IP_ADDRESS", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
    ("PHONE", re.compile(r"(?:\+?\d{1,3}[\s-])?(?:\(?\d{3,5}\)?[\s-])\d{3}[\s-]\d{4}\b")),
]

# Only scrub GENUINELY SENSITIVE entities with Presidio. LOCATION, DATE_TIME,
# and NRP (nationality/religion) are legitimate answer content — restricting
# to this list is what fixes INC-013.
_SENSITIVE_ENTITIES = ["EMAIL_ADDRESS", "PHONE_NUMBER", "CREDIT_CARD", "US_SSN"]

# maps Presidio's entity names back to our internal labels, so hit-counts use
# one consistent naming scheme regardless of which detector found them.
_PRESIDIO_TO_LABEL = {
    "EMAIL_ADDRESS": "EMAIL",
    "PHONE_NUMBER": "PHONE",
    "CREDIT_CARD": "CREDIT_CARD",
    "US_SSN": "US_SSN",
}

_ANALYZER = None
_ANONYMIZER = None


def _regex_scrub(text: str, types: list[str]) -> tuple[str, dict[str, int]]:
    """Fast regex-only scrub. Always available, no dependencies."""
    hits: dict[str, int] = {}
    for name, rx in _PII:
        if name in types:
            text, n = rx.subn(f"<{name}>", text)
            if n:
                hits[name] = hits.get(name, 0) + n
    return text, hits


def _presidio_scrub(text: str) -> tuple[str, dict[str, int]]:
    """Presidio, restricted to sensitive entities only (never LOCATION/DATE_TIME/NRP)."""
    global _ANALYZER, _ANONYMIZER
    if _ANALYZER is None:
        from presidio_analyzer import AnalyzerEngine
        from presidio_anonymizer import AnonymizerEngine

        _ANALYZER = AnalyzerEngine()
        _ANONYMIZER = AnonymizerEngine()

    # entities=... is the fix: only look for sensitive types, never LOCATION/DATE_TIME/NRP
    results = _ANALYZER.analyze(text=text, entities=_SENSITIVE_ENTITIES, language="en")
    if not results:
        return text, {}
    anonymized = _ANONYMIZER.anonymize(text=text, analyzer_results=results)
    hits: dict[str, int] = {}
    for r in results:
        label = _PRESIDIO_TO_LABEL.get(r.entity_type, r.entity_type)
        hits[label] = hits.get(label, 0) + 1
    return anonymized.text, hits


def scrub(text: str, types: list[str], use_presidio: bool) -> tuple[str, dict[str, int]]:
    """Presidio (sensitive entities only) THEN regex backstop (always runs).

    If Presidio is unavailable (no spaCy model, import error, etc.) we fall
    back to regex-only — and print a visible warning, so degraded PII coverage
    is an observable signal in the logs, never silent (see INC-013: silence
    let a coverage gap go unnoticed).
    """
    hits: Counter = Counter()
    if use_presidio:
        try:
            text, presidio_hits = _presidio_scrub(text)
            hits.update(presidio_hits)
        except Exception as exc:  # noqa: BLE001 - degrade loudly, not silently
            print(f"[curate] WARNING: Presidio unavailable ({exc}); using regex-only PII scrub")

    regex_text, regex_hits = _regex_scrub(text, types)
    # if Presidio already ran, regex still re-scans its output as a backstop
    #text = regex_text if use_presidio else regex_text
    #hits.update({k: hits.get(k, 0) + v for k, v in regex_hits.items()})

    text, regex_hits = _regex_scrub(text, types)
    for k, v in regex_hits.items():
        hits[k] = hits.get(k, 0) + v

    return text, dict(hits)


def build_user_text(record: dict) -> str:
    """Combine Alpaca `instruction` (+ optional `input`) into one user message."""
    instruction = record.get("instruction", "").strip()
    extra = record.get("input", "").strip()
    if extra:
        return f"{instruction}\n\nContext: {extra}"
    return instruction


def main() -> None:
    cfg = load_data_cfg()
    f = cfg["filters"]
    pii = cfg["pii"]

    with open(INGESTED, encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh if line.strip()]

    stats: Counter = Counter()
    pii_totals: Counter = Counter()
    kept: list[dict] = []

    for r in rows:
        stats["total"] += 1
        user_text = build_user_text(r)
        response = r.get("output", "")

        # --- quality gates (drop-and-count) ---
        bad, reason = bad_length(response, f["min_chars"], f["max_chars"])
        if bad:
            stats[f"response_{reason}"] += 1
            continue
        if len(user_text.strip()) < f["min_chars"]:
            stats["prompt_too_short"] += 1
            continue

        wrong, lang = wrong_language(f"{user_text} {response}", f["allowed_languages"])
        if wrong:
            stats["wrong_language"] += 1
            continue
        if is_refusal(response, f["refusal_markers"]):
            stats["refusal"] += 1
            continue
        if is_echo(user_text, response, f["echo_overlap"]):
            stats["echo"] += 1
            continue
        if is_repetitive(response, f["max_repetition_ratio"], f["min_words_for_repetition"]):
            stats["repetition"] += 1
            continue
        if is_truncated(response, f["min_chars_for_truncation"]):
            stats["truncation"] += 1
            continue

        # --- PII scrub every kept record ---
        s_user, h1 = scrub(user_text, pii["scrub_types"], pii["use_presidio"])
        s_response, h2 = scrub(response, pii["scrub_types"], pii["use_presidio"])
        merged: dict[str, int] = {}
        for h in (h1, h2):
            for k, v in h.items():
                merged[k] = merged.get(k, 0) + v
                pii_totals[k] += v

        kept.append(
            {
                "id": r.get("id"),
                "instruction": s_user,   # combined user message
                "response": s_response,  # the answer
                "language": lang,
                "pii_hits": merged,
            }
        )
        stats["kept"] += 1

    CURATED.parent.mkdir(parents=True, exist_ok=True)
    with open(CURATED, "w", encoding="utf-8") as fh:
        for rec in kept:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "counts": dict(stats),
        "pii_removed": dict(pii_totals),
    }
    with open(REPORT, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)

    print(f"[curate] kept {stats['kept']}/{stats['total']} · PII removed: {dict(pii_totals)}")
    print(f"[curate] report -> {REPORT}")


if __name__ == "__main__":
    main()
