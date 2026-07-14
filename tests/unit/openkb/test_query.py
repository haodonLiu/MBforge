from __future__ import annotations

import os
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import pytest

from mbforge.openkb import query as openkb_query
from mbforge.utils.config import AppConfig, LLMConfig


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


def test_extract_relevant_sources_skips_oversized_files(tmp_path: Path) -> None:
    """Oversized wiki files are skipped instead of being read into memory."""
    wiki = tmp_path / "wiki"
    summaries = wiki / "summaries"
    summaries.mkdir(parents=True)
    normal = summaries / "doc1.md"
    normal.write_text("# Title\nThis document mentions aspirin.")
    huge = summaries / "doc2.md"
    huge.write_bytes(b"x" * (openkb_query._MAX_WIKI_FILE_BYTES + 1))
    result = openkb_query._extract_relevant_sources("aspirin", str(wiki), 5)
    assert len(result) == 1
    assert result[0]["id"] == "doc1"


def test_extract_relevant_sources_skips_non_files(tmp_path: Path) -> None:
    """Directories matching the glob pattern are ignored."""
    wiki = tmp_path / "wiki"
    summaries = wiki / "summaries"
    summaries.mkdir(parents=True)
    (summaries / "doc1.md").write_text("# Title\nThis document mentions aspirin.")
    (summaries / "subdir.md").mkdir()
    result = openkb_query._extract_relevant_sources("aspirin", str(wiki), 5)
    assert len(result) == 1
    assert result[0]["id"] == "doc1"


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


@pytest.mark.asyncio
async def test_search_wiki_passes_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """search_wiki must pass credentials explicitly and not mutate os.environ."""
    config = AppConfig(
        llm=LLMConfig(
            model="q-model",
            api_key="q-key",
            base_url="https://q.example/v1",
        )
    )
    monkeypatch.setattr(openkb_query, "load_global_config", lambda: config)
    monkeypatch.setenv("OPENAI_API_KEY", "legacy-key")
    monkeypatch.setenv("OPENAI_API_BASE", "https://legacy.example/v1")

    captured: dict[str, object] = {}

    async def _fake_run_query(**kwargs):
        captured.update(kwargs)
        return "answer"

    fake_module = ModuleType("openkb.agent.query")
    fake_module.run_query = _fake_run_query

    with patch.dict(sys.modules, {"openkb.agent.query": fake_module}):
        result = await openkb_query.search_wiki("question", str(tmp_path))

    assert result["answer"] == "answer"
    assert captured["model"] == "q-model"
    assert captured["api_key"] == "q-key"
    assert captured["api_base"] == "https://q.example/v1"
    assert captured["kb_dir"] == tmp_path
    # The global environment must remain untouched.
    assert os.environ["OPENAI_API_KEY"] == "legacy-key"
    assert os.environ["OPENAI_API_BASE"] == "https://legacy.example/v1"
