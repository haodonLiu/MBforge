from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from mbforge.core import knowledge_base as kb
from mbforge.core.semantic_cache import store_cache


def test_search_cache_hit(in_memory_semantic_cache: str) -> None:
    library_root = in_memory_semantic_cache
    store_cache("query", library_root, [{"id": "cached"}])
    result = kb.search("query", library_root, use_cache=True)
    assert result["from_cache"] is True
    assert result["count"] == 1
    assert result["results"][0]["id"] == "cached"


def test_search_with_doc_id_filter(in_memory_semantic_cache: str) -> None:
    library_root = in_memory_semantic_cache

    def _fake_search(*args, **kwargs):
        return {
            "results": [
                {"doc_id": "doc1", "text": "a"},
                {"doc_id": "doc2", "text": "b"},
            ],
            "answer": "",
        }

    with patch("mbforge.openkb.adapter.OpenKBAdapter.search", _fake_search):
        result = kb.search("q", library_root, doc_id_filter="doc1")
    assert len(result["results"]) == 1
    assert result["results"][0]["doc_id"] == "doc1"


def test_search_adapter_error(in_memory_semantic_cache: str) -> None:
    library_root = in_memory_semantic_cache

    def _broken(*args, **kwargs):
        raise RuntimeError("openkb failed")

    with patch("mbforge.openkb.adapter.OpenKBAdapter.search", _broken):
        result = kb.search("q", library_root)
    assert result["results"] == []
    assert "error" in result
    assert result.get("error_code") == "openkb_search_failed"


def test_search_adapter_unexpected_exception_propagates(
    in_memory_semantic_cache: str,
) -> None:
    """Unexpected exceptions (e.g. TypeError) must not be swallowed."""
    library_root = in_memory_semantic_cache

    def _broken(*args, **kwargs):
        raise TypeError("programming error")

    with (
        pytest.raises(TypeError),
        patch("mbforge.openkb.adapter.OpenKBAdapter.search", _broken),
    ):
        kb.search("q", library_root)


def test_get_document_pages(tmp_path: Path) -> None:
    from mbforge.core.artifact import ArtifactResolver

    library_root = str(tmp_path)
    pages_dir = ArtifactResolver(library_root).pages_dir("doc1")
    pages_dir.mkdir(parents=True)
    (pages_dir / "page_0001.txt").write_text("page one")
    (pages_dir / "page_0002.txt").write_text("page two")
    result = kb.get_document_pages(library_root, "doc1", pages=[1])
    assert len(result) == 1
    assert result[0]["page"] == 1


def test_get_document_tree_from_openkb_wiki(tmp_path: Path) -> None:
    from mbforge.core.layout import LibraryLayout

    library_root = str(tmp_path)
    summary = LibraryLayout(library_root).openkb_wiki_dir() / "summaries" / "doc1.md"
    summary.parent.mkdir(parents=True)
    summary.write_text("# Summary")
    result = kb.get_document_tree(library_root, "doc1")
    assert result is not None
    assert result[0]["source"] == "openkb_wiki"
