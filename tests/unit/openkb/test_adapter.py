"""Tests for the OpenKB adapter facade."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mbforge.openkb.adapter import _MAX_MD_INDEX_BYTES, OpenKBAdapter
from mbforge.utils.helpers import FileAccessError, ValidationError


def test_index_markdown_copies_file(tmp_path: Path) -> None:
    """index_markdown copies a valid markdown file into managed storage."""
    adapter = OpenKBAdapter(str(tmp_path))
    md = tmp_path / "input.md"
    md.write_text("# Hello", encoding="utf-8")

    mock_indexer = MagicMock()
    mock_indexer.add_document.return_value = "doc-id"
    adapter._indexer = mock_indexer  # type: ignore[assignment]

    doc_id = adapter.index_markdown(str(md), doc_id="doc1")

    assert doc_id == "doc-id"
    target = tmp_path / ".mbforge" / "openkb" / "documents" / "doc1.md"
    assert target.exists()
    assert target.read_text(encoding="utf-8") == "# Hello"


def test_index_markdown_missing_file_raises(tmp_path: Path) -> None:
    """index_markdown raises FileNotFoundError for a missing source path."""
    adapter = OpenKBAdapter(str(tmp_path))
    with pytest.raises(FileNotFoundError):
        adapter.index_markdown(str(tmp_path / "missing.md"))


def test_index_markdown_directory_rejected(tmp_path: Path) -> None:
    """index_markdown rejects non-regular files such as directories."""
    adapter = OpenKBAdapter(str(tmp_path))
    directory = tmp_path / "dir.md"
    directory.mkdir()
    with pytest.raises(FileAccessError):
        adapter.index_markdown(str(directory))


def test_index_markdown_oversized_file_rejected(tmp_path: Path) -> None:
    """index_markdown rejects files exceeding the size limit."""
    adapter = OpenKBAdapter(str(tmp_path))
    md = tmp_path / "huge.md"
    md.write_bytes(b"x" * (_MAX_MD_INDEX_BYTES + 1))
    with pytest.raises(ValidationError):
        adapter.index_markdown(str(md))


def test_search_runs_async_query(tmp_path: Path) -> None:
    """search delegates to the async search_wiki wrapper."""
    adapter = OpenKBAdapter(str(tmp_path))
    with patch("mbforge.openkb.adapter.search_wiki") as mock_search:
        mock_search.return_value = {"results": [], "answer": "", "count": 0}
        result = adapter.search("query", top_k=5)
    assert result == {"results": [], "answer": "", "count": 0}
    mock_search.assert_called_once_with("query", str(tmp_path / ".mbforge" / "openkb" / "wiki"), 5)
