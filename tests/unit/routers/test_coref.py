from __future__ import annotations

import shutil
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


def test_coref_figure_labels_validation(app_client: TestClient) -> None:
    resp = app_client.post("/api/v1/coref/figure-labels", json={})
    assert resp.status_code == 422


def test_coref_figure_labels_with_mock(
    app_client: TestClient, tmp_path: Path, sample_pdf: Path
) -> None:
    lib = tmp_path / "lib"
    lib.mkdir()
    shutil.copy(sample_pdf, lib / "doc1.pdf")
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
            json={"library_root": str(lib), "docId": "doc1", "page": 1},
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
    shutil.copy(sample_pdf, lib / "doc1.pdf")
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
            json={"library_root": str(lib), "docId": "doc1", "page": 1},
        )
    assert resp.status_code == 200
    preds = resp.json()["predictions"]
    assert len(preds) == 1
    assert preds[0]["source"] == "geometric_ft"
