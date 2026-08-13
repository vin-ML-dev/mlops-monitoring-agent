# ruff: noqa: E501  (test fixtures use long literal strings)
"""Tests for the Day 1 data pipeline: filters, PII scrub, chat format, split.
The PII tests are the most important — if they go red, stop: you may be about
to train on personal data.
"""

from __future__ import annotations

from src.data import quality_filters as qf
from src.data.build_dataset import to_chat
from src.data.curate import _SENSITIVE_ENTITIES, build_user_text, scrub
from src.data.split import _resolve_counts

REFUSALS = ["as an ai", "i cannot", "i can't", "i am unable"]
PII_TYPES = ["EMAIL", "PHONE", "CREDIT_CARD", "US_SSN", "IP_ADDRESS"]


# ---------------- quality filters ----------------
def test_refusal_detected():
    assert qf.is_refusal("As an AI, I cannot predict stock prices.", REFUSALS)
    assert not qf.is_refusal("A bond is a loan to a company.", REFUSALS)


def test_truncation_detected():
    truncated = "Bonds are lower risk because they pay fixed interest and return principal, although they are still exposed to interest rate and"
    assert qf.is_truncated(truncated, min_chars=40)
    assert not qf.is_truncated("An ETF trades on an exchange.", min_chars=40)


def test_echo_detected():
    q = "What is inflation and how does it work?"
    assert qf.is_echo(q, q, overlap=0.9)
    assert not qf.is_echo(
        q, "Inflation is a rise in prices over time that erodes purchasing power.", overlap=0.9
    )


def test_repetition_detected():
    rep = " ".join(["risk"] * 25)
    assert qf.is_repetitive(rep, max_ratio=0.45, min_words=20)
    normal = "Diversification spreads money across many assets so a loss in one is offset by gains in others over time."
    assert not qf.is_repetitive(normal, max_ratio=0.45, min_words=20)


def test_language_and_length():
    wrong, lang = qf.wrong_language(
        "¿Qué es el interés compuesto y cómo funciona con el tiempo?", ["en"]
    )
    assert wrong and lang != "en"
    bad, reason = qf.bad_length("yes", 15, 4000)
    assert bad and reason == "too_short"


# ---------------- PII scrubbing (most important) ----------------
def test_pii_is_scrubbed():
    text = "Email john@x.com, call (415) 555-0199, card 4111 1111 1111 1111, ssn 123-45-6789"
    clean, hits = scrub(text, PII_TYPES, use_presidio=False)
    for leaked in ["john@x.com", "555-0199", "4111 1111 1111 1111", "123-45-6789"]:
        assert leaked not in clean
    assert hits.get("EMAIL") == 1
    assert hits.get("US_SSN") == 1


def test_clean_text_untouched():
    clean, hits = scrub("What is an index fund?", PII_TYPES, False)
    assert clean == "What is an index fund?"
    assert hits == {}


def test_presidio_entities_are_restricted_to_sensitive_types():
    """INC-013 regression: LOCATION/DATE_TIME/NRP must NEVER be requested from
    Presidio, or real words like "Tokyo" / "Japanese" get replaced with
    placeholders that leak into training answers."""
    assert set(_SENSITIVE_ENTITIES) == {
        "EMAIL_ADDRESS",
        "PHONE_NUMBER",
        "CREDIT_CARD",
        "US_SSN",
    }
    for forbidden in ("LOCATION", "DATE_TIME", "NRP", "PERSON"):
        assert forbidden not in _SENSITIVE_ENTITIES


def test_presidio_failure_falls_back_to_regex_and_warns(monkeypatch, capsys):
    """If Presidio is unavailable, scrubbing must still work (regex backstop)
    and the degradation must be printed, not silent."""
    import src.data.curate as curate_mod

    monkeypatch.setattr(
        curate_mod,
        "_presidio_scrub",
        lambda text: (_ for _ in ()).throw(RuntimeError("no spaCy model")),
    )

    clean, hits = scrub("Email john@x.com please.", PII_TYPES, use_presidio=True)

    assert "john@x.com" not in clean
    assert hits.get("EMAIL") == 1
    out = capsys.readouterr().out
    assert "WARNING" in out and "Presidio unavailable" in out


# ---------------- alpaca instruction+input combine ----------------
def test_build_user_text_combines_input():
    rec = {"instruction": "Summarize the risk.", "input": "High debt, falling revenue."}
    text = build_user_text(rec)
    assert "Summarize the risk." in text and "High debt" in text
    assert build_user_text({"instruction": "Define a bond.", "input": ""}) == "Define a bond."


# ---------------- chat format ----------------
def test_to_chat_shapes_messages():
    rec = {"id": "x", "instruction": "What is an ETF?", "response": "A basket of securities."}
    chat = to_chat(rec, system_prompt="You are helpful.", kind="finance")
    roles = [m["role"] for m in chat["messages"]]
    assert roles == ["system", "user", "assistant"]
    assert chat["meta"]["kind"] == "finance"


# ---------------- split counts ----------------
def test_resolve_counts_exact_when_enough():
    assert _resolve_counts(7000, 5000, 1000, 1000) == (5000, 1000, 1000)


def test_resolve_counts_scales_down_when_small():
    t, v, te = _resolve_counts(70, 5000, 1000, 1000)
    assert t + v + te == 70  # never exceeds the pool
