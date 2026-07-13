from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from mbforge.core.library import LibraryStore
from mbforge.utils.helpers import MBForgeError


def test_library_store_get_singleton(tmp_path: Path) -> None:
    store1 = LibraryStore.get(tmp_path)
    store2 = LibraryStore.get(tmp_path)
    assert store1 is store2


def test_add_document_and_get(tmp_path: Path) -> None:
    store = LibraryStore.get(tmp_path)
    src = tmp_path / "input.pdf"
    src.write_bytes(b"pdf content")
    doc = store.add_document(src, title="My Paper")
    assert doc.doc_id
    assert doc.title == "My Paper"
    retrieved = store.get_document(doc.doc_id)
    assert retrieved is not None
    assert retrieved.title == "My Paper"


def test_add_document_missing_file(tmp_path: Path) -> None:
    store = LibraryStore.get(tmp_path)
    with pytest.raises(MBForgeError):
        store.add_document(tmp_path / "missing.pdf")


def test_add_uploaded_file_and_dedup(tmp_path: Path) -> None:
    store = LibraryStore.get(tmp_path)
    store.add_uploaded_file(b"same content", "a.pdf")
    with pytest.raises(MBForgeError):
        store.add_uploaded_file(b"same content", "b.pdf")


def test_delete_document(tmp_path: Path) -> None:
    store = LibraryStore.get(tmp_path)
    src = tmp_path / "input.pdf"
    src.write_bytes(b"pdf")
    doc = store.add_document(src)
    store.delete_document(doc.doc_id)
    assert store.get_document(doc.doc_id) is None


def test_list_and_search_documents(tmp_path: Path) -> None:
    store = LibraryStore.get(tmp_path)
    src = tmp_path / "input.pdf"
    src.write_bytes(b"pdf")
    store.add_document(src, title="Alpha Paper")
    assert len(store.list_documents()) == 1
    assert len(store.search_documents("Alpha")) == 1
    assert len(store.search_documents("Beta")) == 0


def test_collection_tree(tmp_path: Path) -> None:
    store = LibraryStore.get(tmp_path)
    root = store.create_collection("Root")
    child = store.create_collection("Child", parent_id=root.collection_id)
    tree = store.get_collection_tree()
    assert len(tree) == 1
    assert tree[0].collection_id == root.collection_id
    assert tree[0].children[0].collection_id == child.collection_id


def test_add_to_collection(tmp_path: Path) -> None:
    store = LibraryStore.get(tmp_path)
    src = tmp_path / "input.pdf"
    src.write_bytes(b"pdf")
    doc = store.add_document(src)
    col = store.create_collection("Col")
    store.add_to_collection(col.collection_id, doc.doc_id)
    docs = store.list_documents(collection_id=col.collection_id)
    assert len(docs) == 1


def test_add_uploaded_file_rolls_back_db_on_write_failure(tmp_path: Path) -> None:
    store = LibraryStore.get(tmp_path)
    with (
        patch.object(Path, "write_bytes", side_effect=OSError("disk full")),
        pytest.raises(MBForgeError, match="Failed to store file"),
    ):
        store.add_uploaded_file(b"content", "file.pdf")
    assert store.doc_count() == 0


def test_add_document_rolls_back_db_on_copy_failure(tmp_path: Path) -> None:
    store = LibraryStore.get(tmp_path)
    src = tmp_path / "input.pdf"
    src.write_bytes(b"pdf")
    with (
        patch(
            "mbforge.core.library.shutil.copy2", side_effect=PermissionError("denied")
        ),
        pytest.raises(MBForgeError, match="Failed to store file"),
    ):
        store.add_document(src)
    assert store.doc_count() == 0


def test_delete_document_keeps_db_row_when_storage_move_fails(tmp_path: Path) -> None:
    store = LibraryStore.get(tmp_path)
    src = tmp_path / "input.pdf"
    src.write_bytes(b"pdf")
    doc = store.add_document(src)
    with (
        patch("mbforge.core.library.shutil.move", side_effect=OSError("locked")),
        pytest.raises(MBForgeError, match="Failed to remove document storage"),
    ):
        store.delete_document(doc.doc_id)
    assert store.get_document(doc.doc_id) is not None
    assert Path(store.storage_path(doc.doc_id)).exists()


def test_search_documents_escapes_like_wildcards(tmp_path: Path) -> None:
    """Queries containing % or _ should not be treated as LIKE wildcards."""
    store = LibraryStore.get(tmp_path)
    store.add_uploaded_file(b"a", "a.pdf", title="100% solution")
    store.add_uploaded_file(b"b", "b.pdf", title="100 percent solution")

    matches = store.search_documents("100%")
    assert len(matches) == 1
    assert matches[0].title == "100% solution"

    matches = store.search_documents("100_")
    assert len(matches) == 0
