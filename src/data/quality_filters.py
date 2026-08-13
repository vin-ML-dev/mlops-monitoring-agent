"""Step 2a — QUALITY FILTERS (pure, testable functions).

Each function answers one yes/no question about a record. They are kept pure
(no file I/O) so they are trivial to unit-test. curate.py calls them in order.

The six checks: refusal, truncation, echo, repetition, language, length.
"""

from __future__ import annotations


def _norm(text: str) -> str:
    """Lowercase + collapse whitespace, for stable comparisons."""
    return " ".join(text.lower().split())


def is_refusal(response: str, markers: list[str]) -> bool:
    """True if the reply is low-quality 'won't answer' boilerplate."""
    head = _norm(response)[:100]
    return any(m in head for m in markers)


def is_truncated(response: str, min_chars: int) -> bool:
    """True if a long reply seems cut off mid-sentence.

    Heuristic: only checked on longer replies; flagged when the last character
    is a letter/digit or a comma (i.e. no sentence-ending punctuation).
    """
    r = response.rstrip()
    if len(r) < min_chars:
        return False
    return r[-1].isalnum() or r[-1] == ","


def is_echo(instruction: str, response: str, overlap: float) -> bool:
    """True if the reply just parrots the customer's message."""
    a, b = _norm(instruction), _norm(response)
    if not a or not b:
        return False
    if a == b:
        return True
    wa, wb = set(a.split()), set(b.split())
    union = len(wa | wb)
    return union > 0 and len(wa & wb) / union >= overlap


def is_repetitive(response: str, max_ratio: float, min_words: int) -> bool:
    """True if a reply loops the same words (low unique/total ratio)."""
    words = _norm(response).split()
    if len(words) < min_words:
        return False
    return len(set(words)) / len(words) < max_ratio


def detect_language(text: str) -> str:
    """Return a language code like 'en', or 'unknown' if detection fails."""
    from langdetect import DetectorFactory, LangDetectException, detect

    DetectorFactory.seed = 0  # deterministic
    try:
        return detect(text)
    except LangDetectException:
        return "unknown"


def wrong_language(text: str, allowed: list[str]) -> tuple[bool, str]:
    """Return (is_wrong, detected_language)."""
    lang = detect_language(text)
    return lang not in allowed, lang


def bad_length(text: str, min_chars: int, max_chars: int) -> tuple[bool, str | None]:
    """Return (is_bad, reason) where reason is 'too_short' / 'too_long' / None."""
    n = len(text.strip())
    if n < min_chars:
        return True, "too_short"
    if n > max_chars:
        return True, "too_long"
    return False, None
