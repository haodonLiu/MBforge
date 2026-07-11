"""Unit tests for molecule extraction from text and PDF images."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mbforge.pipeline.extract_molecules import (
    extract_molecules_from_pdf,
    extract_molecules_from_text,
)


def test_extract_molecules_from_text_finds_valid_smiles() -> None:
    """SMILES embedded in plain text are extracted and canonicalized."""
    text = "The ethanol molecule is CCO and propane is CCC"
    results = extract_molecules_from_text(text, doc_id="doc-1")

    canonicals = {r.esmiles for r in results}
    assert "CCO" in canonicals
    assert "CCC" in canonicals
    assert all(r.source == "text" for r in results)


def test_extract_molecules_from_text_ignores_invalid_tokens() -> None:
    """Random alphanumeric tokens that are not valid SMILES are skipped."""
    text = "Some abbreviations like ATP and NADPH should not parse."
    results = extract_molecules_from_text(text, doc_id="doc-1")
    assert results == []


def _patch_pdf_dependencies(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Set up sys.modules mocks so extract_molecules_from_pdf avoids heavy imports."""
    fake_fitz = MagicMock()
    fake_fitz.FileDataError = Exception

    fake_molscribe = MagicMock()
    fake_scribe = MagicMock()
    fake_scribe.esmiles = "CCO"
    fake_scribe.scribe_conf = 0.88
    fake_molscribe.predict.return_value = fake_scribe

    monkeypatch.setitem(sys.modules, "fitz", fake_fitz)
    fake_bbox = MagicMock()
    fake_bbox.category_id = 1
    fake_bbox.bbox = [0.1, 0.1, 0.9, 0.9]
    fake_bbox.score = 0.95

    fake_coref = MagicMock()
    fake_coref.bboxes = [fake_bbox]

    return {
        "fitz": fake_fitz,
        "molscribe": fake_molscribe,
        "coref": fake_coref,
        "scribe": fake_scribe,
    }


def test_extract_molecules_from_pdf_mocked_backends(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Image extraction yields ExtractionResult objects without loading models."""
    mocks = _patch_pdf_dependencies(monkeypatch)

    project_root = str(tmp_path)
    pdf_path = str(tmp_path / "dummy.pdf")
    Path(pdf_path).write_text("dummy")

    fake_page = MagicMock()
    fake_page.rect.width = 612.0
    fake_page.rect.height = 792.0
    fake_page.get_text.return_value = ""
    fake_page.get_images.return_value = []

    fake_pix = MagicMock()
    fake_pix.width = 2
    fake_pix.height = 2
    fake_pix.n = 3
    fake_pix.samples = bytes([255] * 12)
    fake_page.get_pixmap.return_value = fake_pix

    fake_doc = MagicMock()
    fake_doc.__len__ = MagicMock(return_value=1)
    fake_doc.load_page.return_value = fake_page
    mocks["fitz"].open.return_value = fake_doc

    with (
        patch("mbforge.backends.molscribe", new=mocks["molscribe"]),
        patch("mbforge.backends.moldet_v2_ft.MolDetv2FTDetector") as mock_detector_cls,
        patch("mbforge.core.resource_manager.ResourceManager"),
        patch(
            "mbforge.parsers.molecule.coref_alt.detect_coref_via_ft_detector",
            return_value=mocks["coref"],
        ),
        patch(
            "mbforge.parsers.molecule.preprocess.preprocess_mol_image",
            side_effect=lambda x: x,
        ),
    ):
        mock_detector = MagicMock()
        mock_detector.is_available.return_value = True
        mock_detector_cls.return_value = mock_detector

        results = extract_molecules_from_pdf(pdf_path, project_root, "doc-1")

    assert len(results) == 1
    result = results[0]
    assert result.esmiles == "CCO"
    assert result.source == "image"
    assert result.moldet_conf == 0.95
    assert result.scribe_conf == 0.88
    assert result.composite_conf == pytest.approx(0.95 * 0.88)
    assert result.page_idx == 0


def test_extract_molecules_from_pdf_skips_pure_text_pages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pages with abundant native text and no images are skipped."""
    mocks = _patch_pdf_dependencies(monkeypatch)

    project_root = str(tmp_path)
    pdf_path = str(tmp_path / "dummy.pdf")
    Path(pdf_path).write_text("dummy")

    fake_page = MagicMock()
    fake_page.rect.width = 612.0
    fake_page.rect.height = 792.0
    fake_page.get_text.return_value = "A" * 1000
    fake_page.get_images.return_value = []

    fake_doc = MagicMock()
    fake_doc.__len__ = MagicMock(return_value=1)
    fake_doc.load_page.return_value = fake_page
    mocks["fitz"].open.return_value = fake_doc

    with (
        patch("mbforge.backends.moldet_v2_ft.MolDetv2FTDetector") as mock_detector_cls,
        patch("mbforge.core.resource_manager.ResourceManager"),
    ):
        mock_detector = MagicMock()
        mock_detector.is_available.return_value = True
        mock_detector_cls.return_value = mock_detector

        results = extract_molecules_from_pdf(pdf_path, project_root, "doc-1")

    assert results == []


def test_extract_molecules_from_pdf_returns_empty_when_detector_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If MolDetv2-FT is unavailable we bail out early with an empty list."""
    _patch_pdf_dependencies(monkeypatch)

    project_root = str(tmp_path)
    pdf_path = str(tmp_path / "dummy.pdf")
    Path(pdf_path).write_text("dummy")

    with (
        patch("mbforge.backends.moldet_v2_ft.MolDetv2FTDetector") as mock_detector_cls,
        patch("mbforge.core.resource_manager.ResourceManager"),
    ):
        mock_detector = MagicMock()
        mock_detector.is_available.return_value = False
        mock_detector_cls.return_value = mock_detector

        results = extract_molecules_from_pdf(pdf_path, project_root, "doc-1")

    assert results == []
