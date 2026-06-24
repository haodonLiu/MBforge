"""Tests for the Zvec backend service."""

from __future__ import annotations

import gc
import shutil
from pathlib import Path

import pytest

from mbforge.backends import zvec_backend as zvec
from mbforge.utils.helpers import ValidationError


@pytest.fixture
def tmp_zvec_path(tmp_path: Path) -> Path:
    """Return a temporary collection path and clean it up after the test."""
    path = tmp_path / "zvec_coll"
    yield path
    zvec.unload()
    gc.collect()
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(autouse=True)
def _reset_zvec_state() -> None:
    """Ensure each test starts with a clean backend state."""
    zvec.unload()
    gc.collect()


def _open(tmp_path: Path, dim: int = 4) -> None:
    """Helper to open a collection on a fresh path."""
    if tmp_path.exists():
        shutil.rmtree(tmp_path)
    zvec.load()
    zvec.open_collection(str(tmp_path), dim)


def test_load_initializes_runtime() -> None:
    zvec.load()
    assert zvec.health()["status"] == "ready"
    assert zvec.health()["error"] == ""


def test_unload_clears_state() -> None:
    zvec.load()
    zvec.unload()
    assert zvec.health()["status"] == "loading"


def test_open_collection_requires_path_and_dim(tmp_zvec_path: Path) -> None:
    zvec.load()
    with pytest.raises(ValidationError):
        zvec.open_collection("", 4)
    with pytest.raises(ValidationError):
        zvec.open_collection(str(tmp_zvec_path), 0)


def test_index_document_roundtrip(tmp_zvec_path: Path) -> None:
    _open(tmp_zvec_path)

    result = zvec.index_document(
        "doc1",
        ["doc1__sec0", "doc1__sec1"],
        ["hello world", "foo bar"],
        ['{"title":"Intro"}', '{"title":"Body"}'],
        [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]],
    )
    assert result["indexed"] == 2
    assert zvec.count()["count"] == 2


def test_index_document_replaces_existing_chunks(tmp_zvec_path: Path) -> None:
    _open(tmp_zvec_path)

    zvec.index_document(
        "doc1",
        ["doc1__sec0"],
        ["first version"],
        ['{"title":"Old"}'],
        [[1.0, 0.0, 0.0, 0.0]],
    )
    assert zvec.count()["count"] == 1

    zvec.index_document(
        "doc1",
        ["doc1__sec0", "doc1__sec1"],
        ["second version", "new chunk"],
        ['{"title":"New"}', '{"title":"New2"}'],
        [[0.0, 1.0, 0.0, 0.0], [1.0, 1.0, 0.0, 0.0]],
    )
    assert zvec.count()["count"] == 2


def test_index_document_validates_dimensions(tmp_zvec_path: Path) -> None:
    _open(tmp_zvec_path, dim=4)

    with pytest.raises(ValidationError):
        zvec.index_document(
            "doc1",
            ["doc1__sec0"],
            ["text"],
            ['{}'],
            [[1.0, 0.0, 0.0]],  # wrong dim
        )


def test_delete_document(tmp_zvec_path: Path) -> None:
    _open(tmp_zvec_path)

    zvec.index_document(
        "doc1",
        ["doc1__sec0"],
        ["hello"],
        ['{}'],
        [[1.0, 0.0, 0.0, 0.0]],
    )
    assert zvec.count()["count"] == 1

    result = zvec.delete_document("doc1")
    assert result["deleted"] is True
    assert zvec.count()["count"] == 0


def test_vector_search(tmp_zvec_path: Path) -> None:
    _open(tmp_zvec_path)

    zvec.index_document(
        "doc1",
        ["doc1__sec0", "doc1__sec1"],
        ["hello world", "foo bar"],
        ['{"title":"Intro"}', '{"title":"Body"}'],
        [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]],
    )

    result = zvec.vector_search([1.0, 0.0, 0.0, 0.0], 5)
    results = result["results"]
    assert len(results) == 2
    assert results[0]["id"] == "doc1__sec0"
    assert results[0]["metadata"]["title"] == "Intro"


def test_vector_search_with_doc_filter(tmp_zvec_path: Path) -> None:
    _open(tmp_zvec_path)

    zvec.index_document(
        "doc1",
        ["doc1__sec0"],
        ["hello"],
        ['{}'],
        [[1.0, 0.0, 0.0, 0.0]],
    )
    zvec.index_document(
        "doc2",
        ["doc2__sec0"],
        ["hello too"],
        ['{}'],
        [[1.0, 0.0, 0.0, 0.0]],
    )

    result = zvec.vector_search([1.0, 0.0, 0.0, 0.0], 5, "doc1")
    results = result["results"]
    assert len(results) == 1
    assert results[0]["id"] == "doc1__sec0"


def test_text_search(tmp_zvec_path: Path) -> None:
    _open(tmp_zvec_path)

    zvec.index_document(
        "doc1",
        ["doc1__sec0", "doc1__sec1"],
        ["hello world", "foo bar"],
        ['{"title":"Intro"}', '{"title":"Body"}'],
        [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]],
    )

    result = zvec.text_search("hello", 5)
    results = result["results"]
    assert len(results) >= 1
    ids = {r["id"] for r in results}
    assert "doc1__sec0" in ids


def test_hybrid_search(tmp_zvec_path: Path) -> None:
    _open(tmp_zvec_path)

    zvec.index_document(
        "doc1",
        ["doc1__sec0", "doc1__sec1"],
        ["hello world", "foo bar"],
        ['{"title":"Intro"}', '{"title":"Body"}'],
        [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]],
    )

    result = zvec.hybrid_search([1.0, 0.0, 0.0, 0.0], "hello world", 5)
    results = result["results"]
    assert len(results) >= 1
    assert results[0]["id"] == "doc1__sec0"


def test_count_empty_collection(tmp_zvec_path: Path) -> None:
    _open(tmp_zvec_path)
    assert zvec.count()["count"] == 0


def test_search_requires_open_collection() -> None:
    zvec.unload()
    with pytest.raises(ValidationError):
        zvec.vector_search([1.0, 0.0, 0.0, 0.0], 5)
