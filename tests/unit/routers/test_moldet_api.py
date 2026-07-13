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
    app_client: TestClient, tmp_library: Path, sample_pdf: Path
) -> None:
    doc_id = _import_sample(app_client, tmp_library, sample_pdf)

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
        mock_predict.return_value.scribe_conf = 0.87
        resp = app_client.post(
            "/api/v1/moldet/extract-pdf-page",
            json={
                "library_root": str(tmp_library),
                "doc_id": doc_id,
                "page": 1,
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert len(data["molecules"]) == 1
    assert data["molecules"][0]["smiles"] == "CCO"
    assert data["molecules"][0]["scribe_conf"] == 0.87
    assert data["page_num"] == 1


def test_extract_pdf_page_coref_label_mapping_with_mixed_order(
    app_client: TestClient, tmp_library: Path, sample_pdf: Path
) -> None:
    """Molecule boxes must map to coref labels using original bboxes indices.

    The FT detector may emit identifiers before molecules. ``mol_boxes_px``
    filters to category_id=1 only, so its list index differs from the
    original index in ``coref_result.bboxes``. The router must use the
    original index when looking up label text, otherwise molecules are
    paired with the wrong identifier text.
    """
    doc_id = _import_sample(app_client, tmp_library, sample_pdf)

    coref_result = CorefResult(
        bboxes=[
            # idt at original index 0 -> should pair with mol at index 1.
            CorefBbox(
                category_id=3,
                bbox=(0.05, 0.05, 0.08, 0.08),
                text="3a",
                score=0.8,
            ),
            # mol at original index 1 -> first molecule in filtered order.
            CorefBbox(category_id=1, bbox=(0.1, 0.1, 0.2, 0.2), score=0.9),
            # idt at original index 2 -> should pair with mol at index 3.
            CorefBbox(
                category_id=3,
                bbox=(0.25, 0.25, 0.28, 0.28),
                text="3b",
                score=0.8,
            ),
            # mol at original index 3 -> second molecule in filtered order.
            CorefBbox(category_id=1, bbox=(0.3, 0.3, 0.4, 0.4), score=0.9),
        ],
        corefs=[(1, 0), (3, 2)],
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
        mock_predict.return_value.scribe_conf = 0.91
        resp = app_client.post(
            "/api/v1/moldet/extract-pdf-page",
            json={
                "library_root": str(tmp_library),
                "doc_id": doc_id,
                "page": 1,
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 2
    molecules = data["molecules"]
    assert len(molecules) == 2
    # First filtered molecule is at original index 1, paired with idt at 0.
    assert molecules[0]["context_text"] == "coref label: 3a"
    assert molecules[0]["smiles"] == "CCO"
    assert molecules[0]["scribe_conf"] == 0.91
    # Second filtered molecule is at original index 3, paired with idt at 2.
    assert molecules[1]["context_text"] == "coref label: 3b"
    assert molecules[1]["smiles"] == "CCO"


def test_extract_pdf_page_unpaired_molecule_has_empty_context(
    app_client: TestClient, tmp_library: Path, sample_pdf: Path
) -> None:
    """Molecules without a coref pair should have empty context_text."""
    doc_id = _import_sample(app_client, tmp_library, sample_pdf)

    coref_result = CorefResult(
        bboxes=[
            CorefBbox(category_id=1, bbox=(0.1, 0.1, 0.2, 0.2), score=0.9),
            CorefBbox(
                category_id=3,
                bbox=(0.3, 0.3, 0.4, 0.4),
                text="3c",
                score=0.8,
            ),
            CorefBbox(category_id=1, bbox=(0.5, 0.5, 0.6, 0.6), score=0.9),
        ],
        # Only the second molecule (original index 2) is paired with the idt.
        corefs=[(2, 1)],
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
        mock_predict.return_value.scribe_conf = 0.0
        resp = app_client.post(
            "/api/v1/moldet/extract-pdf-page",
            json={
                "library_root": str(tmp_library),
                "doc_id": doc_id,
                "page": 1,
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    molecules = data["molecules"]
    assert len(molecules) == 2
    # First molecule (original index 0) has no coref pair.
    assert molecules[0]["context_text"] == ""
    # Second molecule (original index 2) is paired with idt at index 1.
    assert molecules[1]["context_text"] == "coref label: 3c"
