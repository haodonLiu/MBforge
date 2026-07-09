"""Unit tests for OpenKBAdapter."""

from __future__ import annotations

import inspect
from pathlib import Path
from unittest.mock import MagicMock


def test_index_markdown_signature() -> None:
    """index_markdown must exist with the expected signature."""
    from mbforge.openkb.adapter import OpenKBAdapter

    sig = inspect.signature(OpenKBAdapter.index_markdown)
    params = list(sig.parameters.keys())
    assert "self" in params
    assert "md_path" in params
    assert "doc_id" in params
    # Under `from __future__ import annotations`, return annotation is the string "str".
    assert sig.return_annotation in (str, "str")


def test_index_markdown_missing_file_raises(tmp_path: Path) -> None:
    """Missing md_path must raise FileNotFoundError."""
    from mbforge.openkb.adapter import OpenKBAdapter

    adapter = OpenKBAdapter(str(tmp_path))
    missing = tmp_path / "does_not_exist.md"
    try:
        adapter.index_markdown(str(missing))
    except FileNotFoundError:
        return
    raise AssertionError("Expected FileNotFoundError for missing md_path")


def test_index_markdown_copies_and_calls_indexer(tmp_path: Path) -> None:
    """index_markdown must copy .md to documents dir and call add_document."""
    from mbforge.openkb.adapter import OpenKBAdapter

    # Project root with a fake .mbforge/openkb/ tree so the adapter works
    project_root = tmp_path / "proj"
    project_root.mkdir()

    src_md = tmp_path / "input.md"
    src_md.write_text("# Abstract\n\nSome text.\n", encoding="utf-8")

    adapter = OpenKBAdapter(str(project_root))

    # Replace the indexer with a mock so we don't need pageindex installed
    fake_indexer = MagicMock()
    fake_indexer.add_document.return_value = "fake-doc-id-123"
    adapter._indexer = fake_indexer

    result = adapter.index_markdown(str(src_md), doc_id="my-doc")

    assert result == "fake-doc-id-123"
    fake_indexer.add_document.assert_called_once()
    call_args = fake_indexer.add_document.call_args
    # Positional args: (path, doc_id)
    target_path = Path(call_args.args[0])
    assert target_path.name == "my-doc.md"
    assert target_path.parent.name == "documents"
    assert target_path.exists()
    assert target_path.read_text(encoding="utf-8") == src_md.read_text(encoding="utf-8")
    assert call_args.args[1] == "my-doc"


def test_index_markdown_auto_uses_stem_when_no_doc_id(tmp_path: Path) -> None:
    """If doc_id is empty, the file stem is used."""
    from mbforge.openkb.adapter import OpenKBAdapter

    project_root = tmp_path / "proj"
    project_root.mkdir()
    src_md = tmp_path / "auto-named.md"
    src_md.write_text("# Title\n", encoding="utf-8")

    adapter = OpenKBAdapter(str(project_root))
    fake_indexer = MagicMock()
    fake_indexer.add_document.return_value = "auto-id"
    adapter._indexer = fake_indexer

    result = adapter.index_markdown(str(src_md))
    assert result == "auto-id"
    call_args = fake_indexer.add_document.call_args
    assert Path(call_args.args[0]).name == "auto-named.md"
    assert call_args.args[1] == "auto-named"
