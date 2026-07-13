"""Unit tests for extract_activities helper functions."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from mbforge.pipeline import extract_activities as act_mod
from mbforge.pipeline.extract_activities import (
    ActivityRecord,
    _cell_matches_value,
    _enrich_records_with_row_positions,
    _is_local_endpoint,
)
from mbforge.utils import config as config_mod


def test_is_local_endpoint_recognizes_local_hosts() -> None:
    """Local/self-hosted endpoints are identified by provider or hostname."""
    assert _is_local_endpoint("http://localhost:11434/v1") is True
    assert _is_local_endpoint("http://127.0.0.1:11434/v1") is True
    assert _is_local_endpoint("http://127.0.0.1:8000/v1") is True
    assert _is_local_endpoint("http://localhost/v1", provider="ollama") is True
    assert _is_local_endpoint("", provider="ollama") is True
    assert _is_local_endpoint("https://api.openai.com/v1") is False
    assert _is_local_endpoint("") is False


def test_cell_matches_value_exact_numeric() -> None:
    """Exact numeric comparison prevents substring false positives."""
    assert _cell_matches_value("12.5", 12.5) is True
    assert _cell_matches_value("12.5 nM", 12.5) is True
    assert _cell_matches_value("> 1000", 1000) is True
    assert _cell_matches_value("10.20", 10.2) is True
    assert _cell_matches_value("112.5", 12.5) is False
    assert _cell_matches_value("no number", 12.5) is False
    assert _cell_matches_value("", 12.5) is False


def test_enrich_records_uses_exact_value_match() -> None:
    """A value of 12.5 must not match a cell containing 112.5."""
    table_md = "| ID | IC50 (nM) |\n|---|---|\n| 1a | 12.5 |\n| 1b | 112.5 |"
    tables = [(table_md, 1)]
    records = [
        ActivityRecord(
            activity_type="IC50",
            value=12.5,
            value_original=12.5,
            unit="nM",
            operator="=",
            target="EGFR",
            assay_type="enzymatic",
            raw_text="IC50 (nM) EGFR: 12.5",
            confidence=0.9,
            page_num=1,
            evidence_kind="table",
            evidence_bbox=None,
            table_idx=0,
            row_label="1a",
        )
    ]

    enriched = _enrich_records_with_row_positions(tables, records)
    # row_idx is 1-based and counts data rows after the header/separator.
    assert enriched[0].row_idx == 2
    assert enriched[0].col_idx == 1


@pytest.fixture
def _patch_chat_openai(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Patch ChatOpenAI in the langchain_openai namespace and return captured kwargs."""
    captured: list[dict[str, Any]] = [{}]

    class _FakeChatOpenAI:
        def __init__(self, **kwargs: Any) -> None:
            captured[0] = kwargs

        def invoke(self, prompt: str) -> SimpleNamespace:
            return SimpleNamespace(content="[]")

    monkeypatch.setattr("langchain_openai.ChatOpenAI", _FakeChatOpenAI)
    return captured


def test_activity_api_key_sent_to_remote_endpoint(
    monkeypatch: pytest.MonkeyPatch,
    _patch_chat_openai: list[dict[str, Any]],
) -> None:
    """Remote OpenAI-compatible endpoints receive the configured API key."""

    class _FakeLLM:
        model = "gpt-4o-mini"
        provider = "openai_compatible"
        api_key = "real-secret-key"
        base_url = "https://api.example.com/v1"

    class _FakeCfg:
        llm = _FakeLLM()

    monkeypatch.setattr(config_mod, "load_global_config", lambda: _FakeCfg())

    act_mod._parse_table_with_llm("|x|", 0, "gpt-4o-mini")
    assert _patch_chat_openai[0]["api_key"] == "real-secret-key"
    assert _patch_chat_openai[0]["base_url"] == "https://api.example.com/v1"


def test_activity_api_key_masked_for_local_endpoint(
    monkeypatch: pytest.MonkeyPatch,
    _patch_chat_openai: list[dict[str, Any]],
) -> None:
    """Local/self-hosted endpoints must not receive the real API key."""

    class _FakeLLM:
        model = "llama3"
        provider = "ollama"
        api_key = "real-secret-key"
        base_url = "http://localhost:11434/v1"

    class _FakeCfg:
        llm = _FakeLLM()

    monkeypatch.setattr(config_mod, "load_global_config", lambda: _FakeCfg())

    act_mod._parse_table_with_llm("|x|", 0, "llama3")
    assert _patch_chat_openai[0]["api_key"] == "dummy"
    assert _patch_chat_openai[0]["base_url"] == "http://localhost:11434/v1"
