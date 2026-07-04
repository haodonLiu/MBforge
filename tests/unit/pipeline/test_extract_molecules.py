from pathlib import Path
from unittest.mock import MagicMock, patch

import fitz
import pytest

from mbforge.parsers.molecule.extraction_result import ExtractionResult
from mbforge.pipeline.extract_molecules import (
    extract_molecules_from_pdf,
    extract_molecules_from_text,
)


def test_extract_molecules_from_pdf_returns_empty_when_pipeline_unavailable(
    tmp_path: Path,
) -> None:
    with patch("mbforge.backends.moldet.get_moldet", return_value=None):
        results = extract_molecules_from_pdf("dummy.pdf", str(tmp_path), "doc1")
    assert results == []


def test_extract_molecules_from_pdf_returns_empty_on_open_failure(
    tmp_path: Path,
) -> None:
    fake_pipeline = MagicMock()
    fake_pipeline.is_available.return_value = True

    with (
        patch("mbforge.backends.moldet.get_moldet", return_value=fake_pipeline),
        patch.object(fitz, "open") as mock_fitz,
    ):
        mock_fitz.side_effect = RuntimeError("corrupted pdf")
        results = extract_molecules_from_pdf("dummy.pdf", str(tmp_path), "doc1")

    assert results == []


def test_extract_molecules_from_pdf_collects_results(tmp_path: Path) -> None:
    fake_pipeline = MagicMock()
    fake_pipeline.is_available.return_value = True
    source_crop = tmp_path / "crop.png"
    fake_result = ExtractionResult(
        esmiles="CCO",
        name="ethanol",
        source="image",
        moldet_conf=0.9,
        scribe_conf=0.8,
        bbox_pdf=(10.0, 20.0, 30.0, 40.0),
        page_idx=0,
        mol_img_path=source_crop,
        status="pending",
    )
    source_crop.touch()
    fake_pipeline.extract_page.return_value = [fake_result]

    with (
        patch("mbforge.backends.moldet.get_moldet", return_value=fake_pipeline),
        patch.object(fitz, "open") as mock_fitz,
    ):
        mock_page = MagicMock()
        mock_page.rect.width = 595.0
        mock_page.rect.height = 842.0
        mock_pix = MagicMock()
        mock_pix.width = 100
        mock_pix.height = 100
        mock_pix.n = 3
        mock_pix.samples = bytes([0] * 100 * 100 * 3)
        mock_page.get_pixmap.return_value = mock_pix
        mock_doc = MagicMock()
        mock_doc.__len__ = lambda _: 1
        mock_doc.load_page.return_value = mock_page
        mock_doc.__enter__ = MagicMock(return_value=mock_doc)
        mock_doc.__exit__ = MagicMock(return_value=False)
        mock_fitz.return_value = mock_doc

        results = extract_molecules_from_pdf("dummy.pdf", str(tmp_path), "doc1")

    assert len(results) == 1
    assert results[0].esmiles == "CCO"
    assert results[0].page_idx == 0

    crop_dir = tmp_path / ".mbforge" / "crops" / "doc1"
    assert crop_dir.exists()
    expected_crop = crop_dir / "crop.png"
    assert expected_crop.exists()
    assert not source_crop.exists()
    assert results[0].mol_img_path == expected_crop


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


@pytest.mark.parametrize(
    "side_effect", [OSError("permission denied"), RuntimeError("boom")]
)
def test_extract_molecules_from_pdf_keeps_original_path_on_move_failure(
    tmp_path: Path,
    side_effect: Exception,
) -> None:
    fake_pipeline = MagicMock()
    fake_pipeline.is_available.return_value = True
    source_crop = tmp_path / "crop.png"
    fake_result = ExtractionResult(
        esmiles="CCO",
        source="image",
        moldet_conf=0.9,
        scribe_conf=0.8,
        bbox_pdf=(10.0, 20.0, 30.0, 40.0),
        page_idx=0,
        mol_img_path=source_crop,
        status="pending",
    )
    source_crop.touch()
    fake_pipeline.extract_page.return_value = [fake_result]

    with (
        patch("mbforge.backends.moldet.get_moldet", return_value=fake_pipeline),
        patch.object(fitz, "open") as mock_fitz,
        patch("mbforge.pipeline.extract_molecules.shutil.move") as mock_move,
    ):
        mock_move.side_effect = side_effect
        mock_page = MagicMock()
        mock_page.rect.width = 595.0
        mock_page.rect.height = 842.0
        mock_pix = MagicMock()
        mock_pix.width = 100
        mock_pix.height = 100
        mock_pix.n = 3
        mock_pix.samples = bytes([0] * 100 * 100 * 3)
        mock_page.get_pixmap.return_value = mock_pix
        mock_doc = MagicMock()
        mock_doc.__len__ = lambda _: 1
        mock_doc.load_page.return_value = mock_page
        mock_doc.__enter__ = MagicMock(return_value=mock_doc)
        mock_doc.__exit__ = MagicMock(return_value=False)
        mock_fitz.return_value = mock_doc

        results = extract_molecules_from_pdf("dummy.pdf", str(tmp_path), "doc1")

    assert len(results) == 1
    assert results[0].mol_img_path == source_crop
