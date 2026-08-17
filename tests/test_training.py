"""Tests for the parts of Day 2 that don't need a GPU or model download:
data validation, chat rendering, config loading, and the model card.
"""

from __future__ import annotations

from src.training import load_train_cfg
from src.training.data import is_valid_record, load_chat_jsonl, render_chatml
from src.training.model_card import build_model_card

GOOD = {
    "messages": [
        {"role": "system", "content": "You are honest."},
        {"role": "user", "content": "What is an ETF?"},
        {"role": "assistant", "content": "A basket of securities."},
    ],
    "meta": {"kind": "finance"},
}


def test_valid_record_accepts_good():
    assert is_valid_record(GOOD)


def test_valid_record_rejects_no_assistant():
    bad = {"messages": [{"role": "user", "content": "hi there friend"}]}
    assert not is_valid_record(bad)


def test_valid_record_rejects_empty_content():
    bad = {
        "messages": [
            {"role": "user", "content": "  "},
            {"role": "assistant", "content": "hello"},
        ]
    }
    assert not is_valid_record(bad)


def test_render_chatml_has_roles_and_markers():
    text = render_chatml(GOOD["messages"])
    assert "<|im_start|>user" in text
    assert "<|im_start|>assistant" in text
    assert "<|im_end|>" in text


def test_sample_data_loads_and_is_valid():
    rows = load_chat_jsonl("data/processed/train.jsonl")
    assert len(rows) >= 1
    assert all(is_valid_record(r) for r in rows)


def test_config_has_required_fields():
    cfg = load_train_cfg()
    assert cfg["model"]["base_id"] == "Qwen/Qwen3-1.7B"
    assert cfg["lora"]["r"] >= 1
    assert 0 < cfg["train"]["lr"] < 1
    # QLoRA target modules cover attention + MLP
    for mod in ("q_proj", "v_proj", "down_proj"):
        assert mod in cfg["lora"]["target_modules"]


def test_model_card_records_provenance():
    cfg = load_train_cfg()
    card = build_model_card(cfg, data_version="abc1234", gguf=False)
    assert "Qwen/Qwen3-1.7B" in card
    assert "abc1234" in card
    assert "QLoRA" in card


def test_model_card_gguf_variant_lists_quant():
    cfg = load_train_cfg()
    card = build_model_card(cfg, data_version="abc1234", gguf=True)
    assert "GGUF" in card
    assert cfg["gguf"]["quant"] in card
