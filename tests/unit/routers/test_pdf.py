from pathlib import Path

from fastapi.testclient import TestClient


def test_figure_bboxes_returns_page_array(app_client: TestClient, sample_pdf: Path) -> None:
    response = app_client.post(
        "/api/v1/pdf/figure-bboxes",
        json={"pdf_path": str(sample_pdf)},
    )

    assert response.status_code == 200
    assert response.json() == [
        {"page_num": 1, "figures": []},
        {"page_num": 2, "figures": []},
    ]


def test_figure_bboxes_missing_pdf_is_empty(app_client: TestClient) -> None:
    response = app_client.post(
        "/api/v1/pdf/figure-bboxes",
        json={"pdf_path": "C:/missing/sample.pdf"},
    )

    assert response.status_code == 200
    assert response.json() == []
