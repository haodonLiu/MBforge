from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from mbforge.pipeline.extract_text import PageContent, TextSpan
from mbforge.pipeline.normalize import DetectionSource, NormalizedMolecule
from mbforge.pipeline.organizer import (
    _looks_degenerate,
    _rule_based_reorganize,
    insert_molecode_blocks,
    reorganize_with_llm,
)


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
