from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient


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
