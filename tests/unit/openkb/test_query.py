from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import pytest

from mbforge.openkb import query as openkb_query


def test_extract_relevant_sources_empty(tmp_path: Path) -> None:
    result = openkb_query._extract_relevant_sources("test", str(tmp_path), 5)
    assert result == []


def test_extract_relevant_sources_scores(tmp_path: Path) -> None:
    wiki = tmp_path / "wiki"
    summaries = wiki / "summaries"
    summaries.mkdir(parents=True)
    (summaries / "doc1.md").write_text("# Title\nThis document mentions aspirin.")
    result = openkb_query._extract_relevant_sources("aspirin", str(wiki), 5)
    assert len(result) == 1
    assert result[0]["id"] == "doc1"
    assert result[0]["score"] > 0


def test_extract_title() -> None:
    assert openkb_query._extract_title("# Hello\nWorld") == "Hello"
    assert openkb_query._extract_title("No heading") == ""


def test_extract_pages() -> None:
    assert openkb_query._extract_pages("pages 5-10") == (5, 10)
    assert openkb_query._extract_pages("page 3") == (3, 3)
    assert openkb_query._extract_pages("no pages") == (None, None)


@pytest.mark.asyncio
async def test_search_wiki_openkb_missing(tmp_path: Path) -> None:
    fake_module = ModuleType("openkb.agent.query")

    def _raise_on_run_query(name: str) -> None:
        if name == "run_query":
            raise ImportError("openkb")
        raise AttributeError(name)

    fake_module.__getattr__ = _raise_on_run_query

    with (
        patch.dict(sys.modules, {"openkb.agent.query": fake_module}),
        pytest.raises(RuntimeError),
    ):
        await openkb_query.search_wiki("q", str(tmp_path))
