from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


def _make_fake_coref_result() -> MagicMock:
    mol = MagicMock()
    mol.category_id = 1
    mol.bbox = (0.1, 0.1, 0.2, 0.2)
    mol.score = 0.9

    label = MagicMock()
    label.category_id = 3
    label.bbox = (0.3, 0.3, 0.4, 0.4)
    label.score = 0.8

    result = MagicMock()
    result.bboxes = [mol, label]
    result.corefs = [(0, 1)]
    return result


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


def test_coref_figure_labels_validation(app_client: TestClient) -> None:
    resp = app_client.post("/api/v1/coref/figure-labels", json={})
    assert resp.status_code == 422


def test_coref_figure_labels_with_mock(
    app_client: TestClient, tmp_path: Path, sample_pdf: Path
) -> None:
    lib = tmp_path / "lib"
    lib.mkdir()
    doc_id = _import_sample(app_client, lib, sample_pdf)
    fake = _make_fake_coref_result()
    with (
        patch(
            "mbforge.routers.coref.detect_coref_via_ft_detector", return_value=fake
        ),
        patch("mbforge.routers.coref.RapidOCRCropAdapter.instance") as mock_adapter,
    ):
        mock_adapter.return_value.readtext_batch.return_value = ["Fig 1"]
        resp = app_client.post(
            "/api/v1/coref/figure-labels",
            json={"library_root": str(lib), "docId": doc_id, "page": 1},
        )
    assert resp.status_code == 200
    labels = resp.json()["labels"]
    assert len(labels) == 1
    assert labels[0]["label_text"] == "Fig 1"


def test_coref_predictions_with_mock(
    app_client: TestClient, tmp_path: Path, sample_pdf: Path
) -> None:
    lib = tmp_path / "lib"
    lib.mkdir()
    doc_id = _import_sample(app_client, lib, sample_pdf)
    fake = _make_fake_coref_result()
    with (
        patch(
            "mbforge.routers.coref.detect_coref_via_ft_detector", return_value=fake
        ),
        patch("mbforge.routers.coref.RapidOCRCropAdapter.instance") as mock_adapter,
    ):
        mock_adapter.return_value.readtext_batch.return_value = ["Fig 1"]
        resp = app_client.post(
            "/api/v1/coref/predictions",
            json={"library_root": str(lib), "docId": doc_id, "page": 1},
        )
    assert resp.status_code == 200
    preds = resp.json()["predictions"]
    assert len(preds) == 1
    assert preds[0]["source"] == "geometric_ft"
