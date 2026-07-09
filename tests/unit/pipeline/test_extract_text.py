"""Tests for extract_text.py: TextSpan + text_spans on PageContent + write_rough_markdown."""

from __future__ import annotations

from pathlib import Path

from mbforge.pipeline.extract_text import (
    PageContent,
    TextSpan,
    write_rough_markdown,
)


def test_text_span_dataclass() -> None:
    span = TextSpan(text="hello", bbox=(0, 0, 100, 50))
    assert span.text == "hello"
    assert span.bbox == (0, 0, 100, 50)
    assert span.block_type == 0


def test_text_spans_on_page_content() -> None:
    pc = PageContent(page_num=1, text="test")
    assert hasattr(pc, "text_spans")
    assert pc.text_spans == []


def test_write_rough_markdown_creates_file(tmp_path: Path) -> None:
    pages = [
        PageContent(page_num=1, text="Abstract\nThis is a test."),
        PageContent(page_num=2, text="1. Introduction\nSome intro text."),
    ]
    out = tmp_path / "rough.md"
    write_rough_markdown(pages, str(out))
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert "---PAGE 1---" in content or "# " in content
    assert "Abstract" in content or "Introduction" in content
