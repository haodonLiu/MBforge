"""Unit tests for agent tools."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

from mbforge.agent.tools import (
    _compute_molecule_properties_sync,
    compute_molecule_properties,
    get_all_tools,
    get_document_content,
    kb_search,
    list_project_documents,
    molecule_search,
)


def test_get_library_root_extracts_configurable() -> None:
    """library_root is read from the LangGraph configurable block."""
    from mbforge.agent.tools import _get_library_root

    assert _get_library_root({"configurable": {"library_root": "/tmp/lib"}}) == "/tmp/lib"
    assert _get_library_root({}) == ""
    assert _get_library_root(None) == ""


def test_tool_schemas_exclude_config() -> None:
    """The injected ``config`` argument must not appear in LLM-visible schemas."""
    schemas = {t.name: t.args for t in get_all_tools()}
    assert "config" not in schemas.get("kb_search", {})
    assert "config" not in schemas.get("molecule_search", {})
    assert "config" not in schemas.get("get_document_content", {})
    assert "config" not in schemas.get("list_project_documents", {})
    assert "config" not in schemas.get("compute_molecule_properties", {})


@pytest.mark.asyncio
async def test_kb_search_uses_config_library_root(monkeypatch: pytest.MonkeyPatch) -> None:
    """kb_search forwards the configured library_root to the KB search helper."""
    calls: list[tuple[Any, ...]] = []

    def _fake_search(query: str, library_root: str, *, top_k: int, use_cache: bool):
        calls.append((query, library_root, top_k, use_cache))
        return {"results": [{"text": f"result for {query}"}]}

    monkeypatch.setattr("mbforge.core.knowledge_base.search", _fake_search)

    config = {"configurable": {"library_root": "/tmp/kb"}}
    result = await kb_search.coroutine(
        query="aspirin", top_k=3, config=config
    )

    assert len(calls) == 1
    assert calls[0] == ("aspirin", "/tmp/kb", 3, False)
    assert json.loads(result)[0]["text"] == "result for aspirin"


@pytest.mark.asyncio
async def test_kb_search_rejects_missing_library_root() -> None:
    """kb_search returns a structured error when library_root is absent."""
    result = await kb_search.coroutine(query="aspirin", config={})
    assert json.loads(result)["error"] == "library_root not configured"


@pytest.mark.asyncio
async def test_molecule_search_uses_config_library_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """molecule_search builds a request with the configured root and awaits the router."""
    calls: list[Any] = []

    async def _fake_mol_search(request: Any) -> dict:
        calls.append(request)
        return {"results": [{"mol_id": "m1"}]}

    monkeypatch.setattr("mbforge.routers.molecule.mol_search", _fake_mol_search)

    config = {"configurable": {"library_root": "/tmp/mols"}}
    result = await molecule_search.coroutine(query="caffeine", config=config)

    assert len(calls) == 1
    assert calls[0].library_root == "/tmp/mols"
    assert calls[0].query == "caffeine"
    assert json.loads(result)[0]["mol_id"] == "m1"


@pytest.mark.asyncio
async def test_molecule_search_no_new_event_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    """molecule_search never creates a fresh event loop (old anti-pattern removed)."""
    created: list[Any] = []
    original_new_event_loop = asyncio.new_event_loop

    def _tracking_new_event_loop():
        created.append(True)
        return original_new_event_loop()

    monkeypatch.setattr(asyncio, "new_event_loop", _tracking_new_event_loop)
    monkeypatch.setattr(
        "mbforge.routers.molecule.mol_search",
        AsyncMock(return_value={"results": []}),
    )

    await molecule_search.coroutine(
        query="x", config={"configurable": {"library_root": "/tmp"}}
    )

    assert not created


@pytest.mark.asyncio
async def test_get_document_content_uses_config_library_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """get_document_content passes the configured root to the page fetch helper."""
    calls: list[tuple[Any, ...]] = []

    def _fake_get_document_pages(
        library_root: str, doc_id: str, pages: list[int] | None
    ):
        calls.append((library_root, doc_id, pages))
        return [{"page": 1, "text": "hello"}]

    monkeypatch.setattr(
        "mbforge.core.knowledge_base.get_document_pages", _fake_get_document_pages
    )

    config = {"configurable": {"library_root": "/tmp/docs"}}
    result = await get_document_content.coroutine(
        doc_id="d1", pages="1,3", config=config
    )

    assert calls == [("/tmp/docs", "d1", [1, 3])]
    assert json.loads(result)[0]["text"] == "hello"


@pytest.mark.asyncio
async def test_list_project_documents_lists_library_store_docs(
    tmp_library: Path,
) -> None:
    """list_project_documents returns documents from the configured LibraryStore."""
    from mbforge.core.library import LibraryStore

    store = LibraryStore.get(str(tmp_library))
    store.add_uploaded_file(b"pdf", "test.pdf", title="Test")

    config = {"configurable": {"library_root": str(tmp_library)}}
    result = await list_project_documents.coroutine(config=config)

    docs = json.loads(result)
    assert len(docs) == 1
    assert docs[0]["title"] == "Test"
    assert docs[0]["status"] == "pending"


@pytest.mark.asyncio
async def test_list_project_documents_rejects_missing_root() -> None:
    """list_project_documents errors when no library_root is configured."""
    result = await list_project_documents.coroutine(config={})
    assert json.loads(result)["error"] == "library_root not configured"


def test_compute_molecule_properties_offloads_rdkit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The molecule-properties tool runs RDKit work off the event loop."""
    calls: list[tuple[object, tuple, dict]] = []

    async def _fake_to_thread(func, *args, **kwargs):
        calls.append((func, args, kwargs))
        return '{"_fake": true}'

    monkeypatch.setattr(asyncio, "to_thread", _fake_to_thread)

    result = asyncio.run(compute_molecule_properties.ainvoke({"smiles": "CCO"}))

    assert result == '{"_fake": true}'
    assert len(calls) == 1
    assert calls[0][0] is _compute_molecule_properties_sync
    assert calls[0][1] == ("CCO",)


def test_compute_molecule_properties_sync_invalid_smiles() -> None:
    """Invalid SMILES produces a structured error JSON."""
    result = _compute_molecule_properties_sync("not-a-smiles")
    assert json.loads(result)["error"].startswith("Invalid SMILES")


def test_get_all_tools_returns_expected_tools() -> None:
    """The tool registry exports all agent tools."""
    tools = get_all_tools()
    names = {t.name for t in tools}
    assert names == {
        "kb_search",
        "molecule_search",
        "get_document_content",
        "compute_molecule_properties",
        "list_project_documents",
    }
