"""Tests for molecule extraction pipeline stage."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import fitz

from mbforge.parsers.molecule.coref_alt import CorefBbox, CorefResult
from mbforge.pipeline.extract_molecules import (
    extract_molecules_from_pdf,
    extract_molecules_from_text,
)


def _mock_fitz_doc() -> MagicMock:
    """Return a mock fitz Document with one blank page."""
    mock_page = MagicMock()
    mock_page.rect.width = 595.0
    mock_page.rect.height = 842.0
    mock_page.get_text.return_value = ""
    mock_page.get_images.return_value = []

    mock_pix = MagicMock()
    mock_pix.width = 100
    mock_pix.height = 100
    mock_pix.n = 3
    mock_pix.samples = bytes([0] * 100 * 100 * 3)
    mock_page.get_pixmap.return_value = mock_pix

    mock_doc = MagicMock()
    mock_doc.__len__ = lambda _: 1
    mock_doc.load_page.return_value = mock_page
    return mock_doc


def test_extract_molecules_from_pdf_returns_empty_when_detector_unavailable(
    tmp_path: Path,
) -> None:
    with (
        patch("mbforge.core.resource_manager.ResourceManager"),
        patch(
            "mbforge.backends.moldet_v2_ft.MolDetv2FTDetector"
        ) as mock_detector_cls,
    ):
        mock_detector_cls.return_value.is_available.return_value = False
        results = extract_molecules_from_pdf("dummy.pdf", str(tmp_path), "doc1")
    assert results == []


def test_extract_molecules_from_pdf_returns_empty_on_open_failure(
    tmp_path: Path,
) -> None:
    with (
        patch("mbforge.core.resource_manager.ResourceManager"),
        patch(
            "mbforge.backends.moldet_v2_ft.MolDetv2FTDetector"
        ) as mock_detector_cls,
        patch.object(fitz, "open") as mock_fitz_open,
    ):
        mock_detector_cls.return_value.is_available.return_value = True
        mock_fitz_open.side_effect = RuntimeError("corrupted pdf")
        results = extract_molecules_from_pdf("dummy.pdf", str(tmp_path), "doc1")
    assert results == []


def test_extract_molecules_from_pdf_collects_results(tmp_path: Path) -> None:
    coref_result = CorefResult(
        bboxes=[
            CorefBbox(
                category_id=1,
                bbox=(0.1, 0.1, 0.5, 0.5),
                score=0.9,
            )
        ],
        corefs=[],
    )

    with (
        patch("mbforge.core.resource_manager.ResourceManager"),
        patch(
            "mbforge.backends.moldet_v2_ft.MolDetv2FTDetector"
        ) as mock_detector_cls,
        patch(
            "mbforge.parsers.molecule.coref_alt.detect_coref_via_ft_detector",
            return_value=coref_result,
        ),
        patch("mbforge.backends.molscribe.load"),
        patch("mbforge.backends.molscribe.predict") as mock_predict,
        patch.object(fitz, "open") as mock_fitz_open,
    ):
        mock_detector_cls.return_value.is_available.return_value = True
        mock_predict.return_value = MagicMock(esmiles="CCO", scribe_conf=0.8)
        mock_fitz_open.return_value = _mock_fitz_doc()

        results = extract_molecules_from_pdf("dummy.pdf", str(tmp_path), "doc1")

    assert len(results) == 1
    assert results[0].esmiles == "CCO"
    assert results[0].page_idx == 0

    crop_dir = tmp_path / ".mbforge" / "crops" / "doc1"
    assert crop_dir.exists()
    saved_crops = list(crop_dir.glob("*.png"))
    assert len(saved_crops) == 1
    assert results[0].mol_img_path == saved_crops[0]


def test_extract_molecules_from_text_returns_canonical_smiles() -> None:
    results = extract_molecules_from_text(
        "The molecule CCO is ethanol and c1ccccc1 is benzene.", "doc1"
    )
    esmiles_list = [r.esmiles for r in results]
    assert "CCO" in esmiles_list
    assert "c1ccccc1" in esmiles_list
    assert all(r.source == "text" for r in results)


def test_extract_molecules_from_text_returns_empty_for_invalid_text() -> None:
    results = extract_molecules_from_text(
        "This text contains no valid chemical structures.", "doc1"
    )
    assert results == []


def test_extract_molecules_from_text_deduplicates_smiles() -> None:
    results = extract_molecules_from_text("CCO appears twice: CCO", "doc1")
    assert len(results) == 1
    assert results[0].esmiles == "CCO"
