from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from mbforge.parsers.molecule.coref_alt import CorefBbox, CorefResult


def test_extract_pdf_page_validation(app_client: TestClient) -> None:
    resp = app_client.post("/api/v1/moldet/extract-pdf-page", json={})
    assert resp.status_code == 422


def test_extract_pdf_page_with_mock(app_client: TestClient, sample_pdf: Path) -> None:
    coref_result = CorefResult(
        bboxes=[
            CorefBbox(category_id=1, bbox=(0.1, 0.1, 0.2, 0.2), score=0.9),
        ],
        corefs=[],
    )

    with (
        patch(
            "mbforge.routers.moldet_api.detect_coref_via_ft_detector",
            return_value=coref_result,
        ),
        patch("mbforge.backends.molscribe.load"),
        patch("mbforge.backends.molscribe.predict") as mock_predict,
    ):
        mock_predict.return_value.esmiles = "CCO"
        resp = app_client.post(
            "/api/v1/moldet/extract-pdf-page",
            json={"pdf_path": str(sample_pdf), "page": 1},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert len(data["molecules"]) == 1
    assert data["molecules"][0]["smiles"] == "CCO"
    assert data["page_num"] == 1
