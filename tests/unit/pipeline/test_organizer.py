from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from mbforge.pipeline.extract_text import PageContent, TextSpan
from mbforge.pipeline.normalize import DetectionSource, NormalizedMolecule
from mbforge.pipeline.organizer import (
    _llm_complete,
    _looks_degenerate,
    _map_span_idx_to_line,
    _rule_based_reorganize,
    insert_molecode_blocks,
    insert_molecode_blocks_async,
    reorganize_with_llm,
    reorganize_with_llm_async,
)
from mbforge.utils.config import AppConfig, LLMConfig


def test_rule_based_reorganize_strips_page_markers() -> None:
    md = "<!-- PAGE 1 -->\nAbstract\n<!-- PAGE 2 -->\nDetails"
    out = _rule_based_reorganize(md)
    assert "<!-- PAGE" not in out
    assert "Abstract" in out


def test_rule_based_reorganize_promotes_headings() -> None:
    md = "ABSTRACT\n\nSome text"
    out = _rule_based_reorganize(md)
    assert "## Abstract" in out


def test_looks_degenerate_strips_molecode() -> None:
    original = "```molecode\ncontent\n```"
    out = "no molecode here"
    assert _looks_degenerate(out, original) is True


def test_reorganize_with_llm_fallback_on_short_text(tmp_path: Path) -> None:
    md = tmp_path / "in.md"
    out = tmp_path / "out.md"
    md.write_text("# Title\n\nSome content.", encoding="utf-8")
    with patch("mbforge.pipeline.organizer._llm_complete", return_value=None):
        reorganize_with_llm(str(md), str(out))
    assert out.exists()
    assert "# Title" in out.read_text(encoding="utf-8")


def test_reorganize_with_llm_uses_rule_fallback_when_output_too_short(tmp_path: Path) -> None:
    md = tmp_path / "in.md"
    out = tmp_path / "out.md"
    long_text = "Word " * 1000
    md.write_text(long_text, encoding="utf-8")
    with patch("mbforge.pipeline.organizer._llm_complete", return_value="short"):
        reorganize_with_llm(str(md), str(out))
    text = out.read_text(encoding="utf-8")
    assert len(text) > len("short")


def test_insert_molecode_blocks_appends_block(tmp_path: Path) -> None:
    md_path = tmp_path / "in.md"
    out_path = tmp_path / "out.md"
    md_path.write_text("<!-- PAGE 1 -->\nParagraph text.\n", encoding="utf-8")

    pages = [
        PageContent(
            page_num=1,
            text="Paragraph text.",
            text_spans=[TextSpan(text="Paragraph text.", bbox=(0.0, 0.0, 200.0, 20.0))],
        )
    ]
    mol = NormalizedMolecule(
        canonical_smiles="CCO",
        esmiles="CCO",
        name="Ethanol",
        detections=[DetectionSource(source="image", page=0, bbox=(10.0, 0.0, 50.0, 20.0))],
    )

    insert_molecode_blocks(str(md_path), pages, [mol], str(out_path))
    text = out_path.read_text(encoding="utf-8")
    assert "Ethanol" in text
    assert "```" in text


def test_llm_complete_passes_credentials_and_preserves_environ(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_llm_complete must pass api_key/api_base explicitly and not mutate os.environ."""
    from mbforge.utils import config as config_mod

    config = AppConfig(
        llm=LLMConfig(
            model="reorg-model",
            api_key="reorg-key",
            base_url="https://reorg.example/v1",
        )
    )
    monkeypatch.setattr(config_mod, "load_global_config", lambda: config)
    monkeypatch.setenv("OPENAI_API_KEY", "legacy-key")
    monkeypatch.setenv("OPENAI_API_BASE", "https://legacy.example/v1")

    captured: dict[str, object] = {}

    def _fake_completion(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="reorganized"))]
        )

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(completion=_fake_completion))

    result = _llm_complete("reorg-model", "prompt text")

    assert result == "reorganized"
    assert captured["api_key"] == "reorg-key"
    assert captured["api_base"] == "https://reorg.example/v1"
    assert captured["temperature"] == 0.3
    assert captured["messages"] == [{"role": "user", "content": "prompt text"}]
    assert os.environ["OPENAI_API_KEY"] == "legacy-key"
    assert os.environ["OPENAI_API_BASE"] == "https://legacy.example/v1"


def test_insert_molecode_blocks_async_offloads_to_thread(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The async wrapper runs the sync organizer in asyncio.to_thread."""
    calls: list[tuple[object, ...]] = []

    async def _fake_to_thread(func, *args, **kwargs):
        calls.append((func, args, kwargs))
        return str(tmp_path / "out.md")

    monkeypatch.setattr(asyncio, "to_thread", _fake_to_thread)

    result = asyncio.run(
        insert_molecode_blocks_async(str(tmp_path / "in.md"), [], [], str(tmp_path / "out.md"))
    )
    assert result == str(tmp_path / "out.md")
    assert len(calls) == 1
    assert calls[0][0] is insert_molecode_blocks


def test_reorganize_with_llm_async_offloads_to_thread(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The async wrapper runs the LLM reorganization in asyncio.to_thread."""
    calls: list[tuple[object, ...]] = []

    async def _fake_to_thread(func, *args, **kwargs):
        calls.append((func, args, kwargs))
        return str(tmp_path / "out.md")

    monkeypatch.setattr(asyncio, "to_thread", _fake_to_thread)

    result = asyncio.run(
        reorganize_with_llm_async(str(tmp_path / "in.md"), str(tmp_path / "out.md"))
    )
    assert result == str(tmp_path / "out.md")
    assert len(calls) == 1
    assert calls[0][0] is reorganize_with_llm


def test_map_span_idx_to_line_restricts_to_page_boundaries() -> None:
    """The anchor helper searches only within the target page's line range."""
    lines = [
        "<!-- PAGE 1 -->",
        "Page one text.",
        "<!-- PAGE 2 -->",
        "Page two text.",
    ]
    pages = [
        PageContent(
            page_num=1,
            text="Page one text.",
            text_spans=[TextSpan(text="Page one text.", bbox=(0, 0, 100, 20))],
        ),
        PageContent(
            page_num=2,
            text="Page two text.",
            text_spans=[TextSpan(text="Page two text.", bbox=(0, 0, 100, 20))],
        ),
    ]

    assert _map_span_idx_to_line(0, 0, pages, lines) == 1
    assert _map_span_idx_to_line(0, 1, pages, lines) == 3


def test_map_span_idx_to_line_disambiguates_repeated_text() -> None:
    """When the same text occurs multiple times on a page, pick the span-closest line."""
    lines = [
        "<!-- PAGE 1 -->",
        "Repeated text first.",
        "Repeated text second.",
    ]
    pages = [
        PageContent(
            page_num=1,
            text="Repeated text first.\nRepeated text second.",
            text_spans=[
                TextSpan(text="Repeated text first.", bbox=(0, 0, 100, 20)),
                TextSpan(text="Repeated text second.", bbox=(0, 30, 100, 50)),
            ],
        )
    ]

    assert _map_span_idx_to_line(0, 0, pages, lines) == 1
    assert _map_span_idx_to_line(1, 0, pages, lines) == 2
