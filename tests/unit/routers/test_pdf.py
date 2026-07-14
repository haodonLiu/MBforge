from pathlib import Path

from fastapi.testclient import TestClient


def _upload_sample(
    client: TestClient, sample_pdf: Path, filename: str = "sample.pdf"
) -> str:
    """Upload ``sample_pdf`` into the temp library and return its ``doc_id``."""
    with sample_pdf.open("rb") as f:
        response = client.post(
            "/api/v1/library/import",
            files={"file": (filename, f, "application/pdf")},
        )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["success"] is True
    return data["document"]["doc_id"]


def test_figure_bboxes_returns_page_array(
    app_client: TestClient, sample_pdf: Path, tmp_library: Path
) -> None:
    doc_id = _upload_sample(app_client, sample_pdf)

    response = app_client.post(
        "/api/v1/pdf/figure-bboxes",
        json={"library_root": str(tmp_library), "doc_id": doc_id},
    )

    assert response.status_code == 200
    assert response.json() == [
        {"page_num": 1, "figures": []},
        {"page_num": 2, "figures": []},
    ]


def test_figure_bboxes_missing_pdf_is_empty(
    app_client: TestClient, tmp_library: Path
) -> None:
    response = app_client.post(
        "/api/v1/pdf/figure-bboxes",
        json={"library_root": str(tmp_library), "doc_id": "doc-not-found"},
    )

    assert response.status_code == 200
    assert response.json() == []


def test_figure_bboxes_direct_absolute_path_rejected(
    app_client: TestClient, sample_pdf: Path
) -> None:
    response = app_client.post(
        "/api/v1/pdf/figure-bboxes",
        json={"pdf_path": str(sample_pdf)},
    )

    assert response.status_code == 400
    assert response.json()["success"] is False


def test_figure_bboxes_traversal_doc_id_rejected(
    app_client: TestClient, tmp_library: Path
) -> None:
    response = app_client.post(
        "/api/v1/pdf/figure-bboxes",
        json={"library_root": str(tmp_library), "doc_id": "../etc/passwd"},
    )

    assert response.status_code == 400
    assert response.json()["success"] is False
