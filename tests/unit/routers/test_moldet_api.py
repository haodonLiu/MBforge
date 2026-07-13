from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from mbforge.parsers.molecule.coref_alt import CorefBbox, CorefResult


def _import_sample(
    client: TestClient, library_root: Path, sample_pdf: Path
) -> str:
    """Import ``sample_pdf`` into ``library_root`` and return its ``doc_id``."""
    with sample_pdf.open("rb") as f:
        resp = client.post(
            "/api/v1/library/import",
            files={"file": ("sample.pdf", f, "application/pdf")},
            data={"library_root": str(library_root)},
        )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["success"] is True
    return data["document"]["doc_id"]


def test_extract_pdf_page_validation(app_client: TestClient) -> None:
    resp = app_client.post("/api/v1/moldet/extract-pdf-page", json={})
    assert resp.status_code == 422


def test_extract_pdf_page_with_mock(
    app_client: TestClient, tmp_path: Path, sample_pdf: Path
) -> None:
    lib = tmp_path / "lib"
    lib.mkdir()
    doc_id = _import_sample(app_client, lib, sample_pdf)

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
            json={
                "library_root": str(lib),
                "doc_id": doc_id,
                "page": 1,
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert len(data["molecules"]) == 1
    assert data["molecules"][0]["smiles"] == "CCO"
    assert data["page_num"] == 1
