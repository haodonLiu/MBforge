"""Path-traversal hardening for routers listed in Task 1.1.

These tests assert that user-supplied ``library_root``, ``doc_id``,
``pdf_path``, ``rel_path``, and upload ``filename`` values cannot escape
the configured library storage layout.
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

_MALICIOUS_LIBRARY_ROOTS = [
    "..",
    "/etc",
    "C:/Windows",
]


@pytest.mark.parametrize("doc_id", _TRAVERSAL_DOC_IDS)
def test_coref_figure_labels_rejects_traversal_doc_id(
    app_client: TestClient, tmp_library: Path, doc_id: str
) -> None:
    response = app_client.post(
        "/api/v1/coref/figure-labels",
        json={"library_root": str(tmp_library), "doc_id": doc_id, "page": 1},
    )

    assert response.status_code == 400
    assert response.json()["success"] is False


@pytest.mark.parametrize("doc_id", _TRAVERSAL_DOC_IDS)
def test_coref_predictions_rejects_traversal_doc_id(
    app_client: TestClient, tmp_library: Path, doc_id: str
) -> None:
    response = app_client.post(
        "/api/v1/coref/predictions",
        json={"library_root": str(tmp_library), "doc_id": doc_id, "page": 1},
    )

    assert response.status_code == 400
    assert response.json()["success"] is False


@pytest.mark.parametrize("doc_id", _TRAVERSAL_DOC_IDS)
def test_moldet_extract_pdf_rejects_traversal_doc_id(
    app_client: TestClient, tmp_library: Path, doc_id: str
) -> None:
    response = app_client.post(
        "/api/v1/moldet/extract-pdf",
        json={"library_root": str(tmp_library), "doc_id": doc_id, "page": 1},
    )

    assert response.status_code == 400
    assert response.json()["success"] is False


@pytest.mark.parametrize("doc_id", _TRAVERSAL_DOC_IDS)
def test_detection_cache_get_rejects_traversal_doc_id(
    app_client: TestClient, tmp_library: Path, doc_id: str
) -> None:
    response = app_client.post(
        "/api/v1/detection-cache/get",
        json={"library_root": str(tmp_library), "doc_id": doc_id, "page": 1},
    )

    assert response.status_code == 400
    assert response.json()["success"] is False


def test_detection_cache_save_rejects_malicious_doc_id(
    app_client: TestClient, tmp_library: Path
) -> None:
    response = app_client.post(
        "/api/v1/detection-cache/save",
        json={
            "library_root": str(tmp_library),
            "detections": [
                {
                    "mol_id": "mol-1",
                    "doc_id": "../etc/passwd",
                    "page": 1,
                    "bbox_x0": 0.0,
                    "bbox_y0": 0.0,
                    "bbox_x1": 1.0,
                    "bbox_y1": 1.0,
                    "crop_relpath": "crop.png",
                    "conf_moldet": 0.9,
                    "conf_molscribe": 0.8,
                }
            ],
        },
    )

    assert response.status_code == 400
    assert response.json()["success"] is False


@pytest.mark.parametrize(
    "filename",
    [
        "../passwd",
        "..\\autoexec.bat",
        "sub/../passwd.pdf",
        "sub/./file.pdf",
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

    assert response.status_code == 400
    assert response.json()["success"] is False


def test_library_import_accepts_dotted_filename(
    app_client: TestClient, sample_pdf: Path
) -> None:
    """Filenames containing ``..`` as part of a segment (not a traversal
    segment) must be accepted."""
    with sample_pdf.open("rb") as f:
        response = app_client.post(
            "/api/v1/library/import",
            files={"file": ("report..pdf", f, "application/pdf")},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["document"]["file_name"] == "report..pdf"


def test_moldet_extract_pdf_page_rejects_direct_pdf_path(
    app_client: TestClient, sample_pdf: Path
) -> None:
    response = app_client.post(
        "/api/v1/moldet/extract-pdf-page",
        json={"pdf_path": str(sample_pdf), "page": 1},
    )

    assert response.status_code == 400
    assert response.json()["success"] is False


@pytest.mark.parametrize("library_root", _MALICIOUS_LIBRARY_ROOTS)
@pytest.mark.parametrize(
    "endpoint,payload",
    [
        (
            "/api/v1/coref/figure-labels",
            {"doc_id": "doc1", "page": 1},
        ),
        (
            "/api/v1/coref/predictions",
            {"doc_id": "doc1", "page": 1},
        ),
        (
            "/api/v1/moldet/extract-pdf",
            {"doc_id": "doc1", "page": 1},
        ),
        (
            "/api/v1/moldet/extract-pdf-page",
            {"doc_id": "doc1", "page": 1},
        ),
        (
            "/api/v1/detection-cache/get",
            {"doc_id": "doc1", "page": 1},
        ),
    ],
)
def test_endpoints_reject_mismatched_library_root(
    app_client: TestClient,
    library_root: str,
    endpoint: str,
    payload: dict,
) -> None:
    response = app_client.post(
        endpoint,
        json={"library_root": library_root, **payload},
    )

    assert response.status_code == 400
    assert response.json()["success"] is False


@pytest.mark.parametrize("library_root", _MALICIOUS_LIBRARY_ROOTS)
def test_library_import_rejects_mismatched_library_root(
    app_client: TestClient, sample_pdf: Path, library_root: str
) -> None:
    with sample_pdf.open("rb") as f:
        response = app_client.post(
            "/api/v1/library/import",
            files={"file": ("sample.pdf", f, "application/pdf")},
            data={"library_root": library_root},
        )

    assert response.status_code == 400
    assert response.json()["success"] is False


_TRAVERSAL_CROP_PATHS = [
    "../etc/passwd",
    "../../secret",
    "sub/../../../secret",
]


def test_library_crop_rejects_traversal_rel_path(
    app_client: TestClient, tmp_library: Path, sample_pdf: Path
) -> None:
    with sample_pdf.open("rb") as f:
        resp = app_client.post(
            "/api/v1/library/import",
            files={"file": ("sample.pdf", f, "application/pdf")},
        )
    assert resp.status_code == 200
    doc_id = resp.json()["document"]["doc_id"]

    for rel_path in _TRAVERSAL_CROP_PATHS:
        response = app_client.get(
            f"/api/v1/library/documents/{doc_id}/crop",
            params={"rel_path": rel_path, "library_root": str(tmp_library)},
        )
        assert response.status_code == 400, f"rel_path={rel_path!r}"
        assert response.json()["success"] is False
