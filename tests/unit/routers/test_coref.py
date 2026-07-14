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
    app_client: TestClient, tmp_library: Path, sample_pdf: Path
) -> None:
    doc_id = _import_sample(app_client, tmp_library, sample_pdf)
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
            json={"library_root": str(tmp_library), "docId": doc_id, "page": 1},
        )
    assert resp.status_code == 200
    labels = resp.json()["labels"]
    assert len(labels) == 1
    assert labels[0]["label_text"] == "Fig 1"


def test_coref_predictions_with_mock(
    app_client: TestClient, tmp_library: Path, sample_pdf: Path
) -> None:
    doc_id = _import_sample(app_client, tmp_library, sample_pdf)
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
            json={"library_root": str(tmp_library), "docId": doc_id, "page": 1},
        )
    assert resp.status_code == 200
    preds = resp.json()["predictions"]
    assert len(preds) == 1
    assert preds[0]["source"] == "geometric_ft"


def test_coref_persists_and_confirm_survives_refresh(
    app_client: TestClient, tmp_library: Path, sample_pdf: Path
) -> None:
    doc_id = _import_sample(app_client, tmp_library, sample_pdf)
    fake = _make_fake_coref_result()
    with (
        patch(
            "mbforge.routers.coref.detect_coref_via_ft_detector", return_value=fake
        ),
        patch("mbforge.routers.coref.RapidOCRCropAdapter.instance") as mock_adapter,
    ):
        mock_adapter.return_value.readtext_batch.return_value = ["Fig 1"]
        first = app_client.post(
            "/api/v1/coref/predictions",
            json={"library_root": str(tmp_library), "docId": doc_id, "page": 1},
        )
    assert first.status_code == 200
    preds = first.json()["predictions"]
    assert len(preds) == 1
    pred_id = preds[0]["id"]
    assert pred_id >= 1
    assert preds[0]["is_confirmed"] is False

    # Confirm — must hit DB row, not ephemeral id
    conf = app_client.post(
        "/api/v1/coref/confirm-prediction",
        json={
            "libraryRoot": str(tmp_library),
            "predictionId": pred_id,
            "isConfirmed": True,
        },
    )
    assert conf.status_code == 200
    assert conf.json()["is_confirmed"] is True

    # Second read must NOT re-run FT (DB hit) and keep confirmed
    with patch(
        "mbforge.routers.coref.detect_coref_via_ft_detector"
    ) as mock_ft:
        second = app_client.post(
            "/api/v1/coref/predictions",
            json={"library_root": str(tmp_library), "docId": doc_id, "page": 1},
        )
        mock_ft.assert_not_called()
    assert second.status_code == 200
    preds2 = second.json()["predictions"]
    assert len(preds2) == 1
    assert preds2[0]["id"] == pred_id
    assert preds2[0]["is_confirmed"] is True


def test_coref_update_pair_manual(
    app_client: TestClient, tmp_library: Path, sample_pdf: Path
) -> None:
    doc_id = _import_sample(app_client, tmp_library, sample_pdf)
    fake = _make_fake_coref_result()
    with (
        patch(
            "mbforge.routers.coref.detect_coref_via_ft_detector", return_value=fake
        ),
        patch("mbforge.routers.coref.RapidOCRCropAdapter.instance") as mock_adapter,
    ):
        mock_adapter.return_value.readtext_batch.return_value = ["Fig 1"]
        labels_resp = app_client.post(
            "/api/v1/coref/figure-labels",
            json={"library_root": str(tmp_library), "docId": doc_id, "page": 1},
        )
        preds_resp = app_client.post(
            "/api/v1/coref/predictions",
            json={"library_root": str(tmp_library), "docId": doc_id, "page": 1},
        )
    label_id = labels_resp.json()["labels"][0]["id"]
    old_id = preds_resp.json()["predictions"][0]["id"]

    new_resp = app_client.post(
        "/api/v1/coref/update-pair",
        json={
            "libraryRoot": str(tmp_library),
            "docId": doc_id,
            "page": 1,
            "oldPredictionId": old_id,
            "molImageId": None,
            "molSmiles": "CCO",
            "molBbox": [0.1, 0.1, 0.2, 0.2],
            "labelId": label_id,
        },
    )
    assert new_resp.status_code == 200
    new_id = new_resp.json()
    assert isinstance(new_id, int)
    assert new_id != old_id

    preds = app_client.post(
        "/api/v1/coref/predictions",
        json={"library_root": str(tmp_library), "docId": doc_id, "page": 1},
    ).json()["predictions"]
    assert len(preds) == 1
    assert preds[0]["id"] == new_id
    assert preds[0]["source"] == "manual"
    assert preds[0]["is_confirmed"] is True
    assert preds[0]["mol_smiles"] == "CCO"


def test_coref_ensure_for_image(
    app_client: TestClient, tmp_library: Path, sample_pdf: Path
) -> None:
    doc_id = _import_sample(app_client, tmp_library, sample_pdf)
    fake = _make_fake_coref_result()
    with (
        patch(
            "mbforge.routers.coref.detect_coref_via_ft_detector", return_value=fake
        ),
        patch("mbforge.routers.coref.RapidOCRCropAdapter.instance") as mock_adapter,
    ):
        mock_adapter.return_value.readtext_batch.return_value = ["Fig 1"]
        first = app_client.post(
            "/api/v1/coref/ensure-for-image",
            json={
                "libraryRoot": str(tmp_library),
                "docId": doc_id,
                "page": 1,
                "imagePath": "fig.png",
            },
        )
    assert first.status_code == 200
    body = first.json()
    assert body["already_existed"] is False
    assert body["labels_written"] == 1
    assert body["predictions_written"] == 1

    second = app_client.post(
        "/api/v1/coref/ensure-for-image",
        json={
            "libraryRoot": str(tmp_library),
            "docId": doc_id,
            "page": 1,
            "imagePath": "fig.png",
        },
    )
    assert second.status_code == 200
    assert second.json()["already_existed"] is True
    assert second.json()["labels_written"] == 0
