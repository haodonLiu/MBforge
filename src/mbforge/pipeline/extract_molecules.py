"""Molecule extraction from PDF images and text."""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from PIL import Image

from ..parsers.molecule.extraction_result import ExtractionResult
from ..utils.logger import get_logger

if TYPE_CHECKING:
    import fitz

logger = get_logger("mbforge.pipeline.extract_molecules")

DEFAULT_RENDER_DPI = 300.0
_BASE_PDF_DPI = 72.0

_SMILES_LIKE_PATTERN = re.compile(r"[A-Za-z0-9\(\)\[\]\=\#\+\-\\\\/@\.]{3,}")


def extract_molecules_from_pdf(
    pdf_path: str,
    project_root: str,
    doc_id: str,
    max_pages: int | None = None,
) -> list[ExtractionResult]:
    """Render PDF pages and extract molecule structures via MolDet + MolScribe."""
    from ..backends.moldet import get_moldet

    pipeline = get_moldet()
    if pipeline is None or not pipeline.is_available():
        logger.warning(
            "MolDet pipeline unavailable, skipping image molecule extraction"
        )
        return []

    import fitz

    _open_errors: tuple[type[Exception], ...] = (RuntimeError,)
    if hasattr(fitz, "FileDataError"):
        _open_errors = _open_errors + (fitz.FileDataError,)

    crop_dir = Path(project_root) / ".mbforge" / "crops" / doc_id
    crop_dir.mkdir(parents=True, exist_ok=True)

    try:
        doc: fitz.Document = fitz.open(pdf_path)
    except _open_errors as exc:
        logger.error("Failed to open PDF %s: %s", pdf_path, exc)
        return []

    results: list[ExtractionResult] = []

    try:
        pages_to_process = range(min(max_pages or len(doc), len(doc)))
        for page_idx in pages_to_process:
            page = doc.load_page(page_idx)
            zoom = DEFAULT_RENDER_DPI / _BASE_PDF_DPI
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)

            img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                pix.height, pix.width, pix.n
            )
            image = Image.fromarray(img_array)

            page_results = pipeline.extract_page(
                image=image,
                page_idx=page_idx,
                page_w_pts=page.rect.width,
                page_h_pts=page.rect.height,
                image_w=pix.width,
                image_h=pix.height,
                dpi=DEFAULT_RENDER_DPI,
                cache_prefix=f"{doc_id}_page_{page_idx:04d}",
            )

            for r in page_results:
                if r.mol_img_path is not None:
                    target = crop_dir / Path(r.mol_img_path).name
                    if Path(r.mol_img_path) != target:
                        try:
                            shutil.move(str(r.mol_img_path), str(target))
                            r.mol_img_path = target
                        except Exception as move_exc:
                            logger.warning(
                                "Failed to relocate crop image from %s to %s: %s",
                                r.mol_img_path,
                                target,
                                move_exc,
                            )
                    else:
                        r.mol_img_path = target
                r.status = "pending"
                results.append(r)
    finally:
        doc.close()

    logger.info("Extracted %d molecule image candidates from %s", len(results), doc_id)
    return results


def extract_molecules_from_text(text: str, doc_id: str) -> list[ExtractionResult]:
    """Extract SMILES strings from raw text and validate with RDKit."""
    from rdkit import Chem

    results: list[ExtractionResult] = []
    seen: set[str] = set()

    for match in _SMILES_LIKE_PATTERN.finditer(text):
        candidate = match.group(0)
        try:
            mol = Chem.MolFromSmiles(candidate)
            if mol is None:
                continue
            canonical = Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)
        except Exception as exc:
            logger.debug("RDKit failed to parse candidate %r: %s", candidate, exc)
            continue
        if canonical in seen:
            continue
        seen.add(canonical)

        start = max(0, match.start() - 200)
        end = min(len(text), match.end() + 200)
        context = text[start:end]

        results.append(
            ExtractionResult(
                esmiles=canonical,
                name="",
                source="text",
                context_text=context,
                status="pending",
            )
        )

    logger.info("Extracted %d text SMILES candidates from %s", len(results), doc_id)
    return results
