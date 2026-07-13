"""Path-traversal hardening for routers listed in Task 1.1.

These tests assert that user-supplied ``library_root``, ``doc_id``,
``pdf_path``, and upload ``filename`` values cannot escape the library
storage layout.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


_TRAVERSAL_DOC_IDS = [
    "../etc/passwd",
    "..\\Windows\\System32",
    "foo/bar",
    "foo\\bar",
]


@pytest.mark.parametrize("doc_id", _TRAVERSAL_DOC_IDS)
def test_coref_figure_labels_rejects_traversal_doc_id(
    app_client: TestClient, tmp_library: Path, doc_id: str
) -> None:
    response = app_client.post(
        "/api/v1/coref/figure-labels",
        json={"library_root": str(tmp_library), "doc_id": doc_id, "page": 1},
    )

    assert response.status_code in (400, 403, 422, 404)
    assert response.json()["success"] is False


@pytest.mark.parametrize("doc_id", _TRAVERSAL_DOC_IDS)
def test_coref_predictions_rejects_traversal_doc_id(
    app_client: TestClient, tmp_library: Path, doc_id: str
) -> None:
    response = app_client.post(
        "/api/v1/coref/predictions",
        json={"library_root": str(tmp_library), "doc_id": doc_id, "page": 1},
    )

    assert response.status_code in (400, 403, 422, 404)
    assert response.json()["success"] is False


@pytest.mark.parametrize("doc_id", _TRAVERSAL_DOC_IDS)
def test_moldet_extract_pdf_rejects_traversal_doc_id(
    app_client: TestClient, tmp_library: Path, doc_id: str
) -> None:
    response = app_client.post(
        "/api/v1/moldet/extract-pdf",
        json={"library_root": str(tmp_library), "doc_id": doc_id, "page": 1},
    )

    assert response.status_code in (400, 403, 422, 404)
    assert response.json()["success"] is False


@pytest.mark.parametrize("doc_id", _TRAVERSAL_DOC_IDS)
def test_detection_cache_get_rejects_traversal_doc_id(
    app_client: TestClient, tmp_library: Path, doc_id: str
) -> None:
    response = app_client.post(
        "/api/v1/detection-cache/get",
        json={"library_root": str(tmp_library), "doc_id": doc_id, "page": 1},
    )

    assert response.status_code in (400, 403, 422, 404)
    assert response.json()["success"] is False


@pytest.mark.parametrize(
    "filename",
    [
        "../passwd",
        "..\\autoexec.bat",
        "sub/dir/file.pdf",
        "sub\\dir\\file.pdf",
    ],
)
def test_library_import_rejects_traversal_filename(
    app_client: TestClient, sample_pdf: Path, filename: str
) -> None:
    with sample_pdf.open("rb") as f:
        response = app_client.post(
            "/api/v1/library/import",
            files={"file": (filename, f, "application/pdf")},
        )

    assert response.status_code in (400, 403, 422, 404)
    assert response.json()["success"] is False


def test_moldet_extract_pdf_page_rejects_direct_pdf_path(
    app_client: TestClient, sample_pdf: Path
) -> None:
    response = app_client.post(
        "/api/v1/moldet/extract-pdf-page",
        json={"pdf_path": str(sample_pdf), "page": 1},
    )

    assert response.status_code in (400, 403, 422, 404)
    assert response.json()["success"] is False
