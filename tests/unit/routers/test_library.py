from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient


def _assert_error(response, expected_status: int, expected_error_code: str) -> dict:
    assert response.status_code == expected_status, response.text
    data = response.json()
    assert data["success"] is False
    assert data["error_code"] == expected_error_code
    return data


def test_library_status(app_client: TestClient) -> None:
    resp = app_client.get("/api/v1/library/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["configured"] is True
    assert "root" in data


def test_library_configure(app_client: TestClient, tmp_path: Path, monkeypatch) -> None:
    # Isolate the global settings file so the test does not overwrite user config.
    from mbforge.utils import config

    settings_path = tmp_path / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(config, "_SETTINGS_PATH", settings_path)

    root = str(tmp_path / "new_lib")
    resp = app_client.post("/api/v1/library/configure", json={"root": root})
    assert resp.status_code == 200
    assert resp.json()["success"] is True


def test_library_import_and_list(app_client: TestClient) -> None:
    pdf_bytes = b"%PDF-1.4 fake pdf"
    resp = app_client.post(
        "/api/v1/library/import",
        data={"title": "Test Paper"},
        files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    doc_id = data["document"]["doc_id"]

    resp = app_client.post("/api/v1/library/documents", json={})
    assert resp.status_code == 200
    ids = {d["doc_id"] for d in resp.json()["documents"]}
    assert doc_id in ids


def test_library_get_document_file(app_client: TestClient) -> None:
    pdf_bytes = b"%PDF-1.4 fake pdf"
    resp = app_client.post(
        "/api/v1/library/import",
        files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
    )
    doc_id = resp.json()["document"]["doc_id"]
    resp = app_client.get(f"/api/v1/library/documents/{doc_id}/file")
    assert resp.status_code == 200
    assert resp.content == pdf_bytes


def test_library_get_document_reorganized(app_client: TestClient, tmp_library: Path) -> None:
    pdf_bytes = b"%PDF-1.4 fake pdf"
    resp = app_client.post(
        "/api/v1/library/import",
        files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
    )
    doc_id = resp.json()["document"]["doc_id"]

    resp = app_client.get(f"/api/v1/library/documents/{doc_id}/reorganized")
    assert resp.status_code == 404

    reorganized = tmp_library / "storage" / doc_id / "reorganized.md"
    reorganized.parent.mkdir(parents=True, exist_ok=True)
    reorganized.write_text("# Reorganized", encoding="utf-8")
    resp = app_client.get(f"/api/v1/library/documents/{doc_id}/reorganized")
    assert resp.status_code == 200
    assert "# Reorganized" in resp.text


def test_library_collections(app_client: TestClient) -> None:
    resp = app_client.post("/api/v1/library/collections/create", json={"name": "My Col"})
    assert resp.status_code == 200
    col_id = resp.json()["collection"]["collection_id"]

    resp = app_client.post("/api/v1/library/collections/list", json={})
    assert any(c["collection_id"] == col_id for c in resp.json()["collections"])


def test_library_delete_document_missing_doc_id_returns_422(app_client: TestClient) -> None:
    _assert_error(
        app_client.post("/api/v1/library/documents/delete", json={}),
        422,
        "validation_error",
    )


def test_library_delete_collection_missing_id_returns_422(app_client: TestClient) -> None:
    _assert_error(
        app_client.post("/api/v1/library/collections/delete", json={}),
        422,
        "validation_error",
    )


def test_library_delete_collection_unknown_id_returns_404(app_client: TestClient) -> None:
    _assert_error(
        app_client.post(
            "/api/v1/library/collections/delete",
            json={"collection_id": "no-such-collection"},
        ),
        404,
        "not_found",
    )


def test_library_add_document_to_unknown_collection_returns_404(
    app_client: TestClient,
) -> None:
    _assert_error(
        app_client.post(
            "/api/v1/library/collections/add-document",
            json={"collection_id": "no-such-collection", "doc_id": "no-such-doc"},
        ),
        404,
        "not_found",
    )


def test_library_import_duplicate_returns_409(app_client: TestClient) -> None:
    pdf_bytes = b"%PDF-1.4 fake pdf"
    resp = app_client.post(
        "/api/v1/library/import",
        data={"title": "Test Paper"},
        files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
    )
    assert resp.status_code == 200

    resp = app_client.post(
        "/api/v1/library/import",
        data={"title": "Duplicate"},
        files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
    )
    _assert_error(resp, 409, "conflict")


def test_library_configure_missing_root_returns_422(app_client: TestClient) -> None:
    _assert_error(
        app_client.post("/api/v1/library/configure", json={}),
        422,
        "validation_error",
    )
