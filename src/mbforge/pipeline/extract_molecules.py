"""Molecule extraction from PDF images and text."""

from __future__ import annotations

import re
import shutil  # noqa: F401 — imported here so tests can patch `mbforge.pipeline.extract_molecules.shutil.move`
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from PIL import Image

from ..parsers.molecule.extraction_result import ExtractionResult
from ..utils.logger import get_logger

if TYPE_CHECKING:
    import fitz

logger = get_logger("mbforge.pipeline.extract_molecules")

# 分子检测渲染分辨率（200 DPI 在检测精度损失 <5% 的前提下提升渲染速度 ~50%）
DEFAULT_RENDER_DPI = 200.0
_BASE_PDF_DPI = 72.0

# 纯文本页跳过阈值：文本量超过此值且无嵌入图 → 跳过分子检测
_TEXT_PAGE_CHAR_THRESHOLD = 500

_SMILES_LIKE_PATTERN = re.compile(r"[A-Za-z0-9\(\)\[\]\=\#\+\-\\\\/@\.]{3,}")


def extract_molecules_from_pdf(
    pdf_path: str,
    project_root: str,
    doc_id: str,
    max_pages: int | None = None,
) -> list[ExtractionResult]:
    """Render PDF pages and extract molecule structures via MolDetv2-FT + MolScribe.

    The legacy Doc+General detector pipeline (MolImagePipeline.extract_page)
    was replaced by the joint MolDetv2-FT detector on 2026-07-08. This
    function now mirrors /api/v1/moldet/extract-pdf-page but is driven by
    the in-process pipeline runner (no HTTP round-trip) and writes crop
    images to {project_root}/.mbforge/crops/{doc_id}/ for downstream
    pipeline stages.
    """
    from ..backends import molscribe
    from ..backends.moldet_v2_ft import MolDetv2FTDetector
    from ..core.resource_manager import ResourceManager
    from ..parsers.molecule.coref_alt import detect_coref_via_ft_detector

    # 确保模型已下载（首次运行从 ModelScope 自动拉取）
    ResourceManager.ensure("moldet")
    # 确保 MoleCode 包已安装（生成 SMILES → Mermaid blocks）
    ResourceManager.ensure("molecode")

    # 从 config 读取检测参数（回退到硬编码默认值）
    try:
        from ..utils.config import load_global_config

        _cfg = load_global_config()
        _moldet_cfg = _cfg.moldet or {}
        _render_dpi = float(_moldet_cfg.get("detection_dpi", DEFAULT_RENDER_DPI))
        _detection_batch_size = int(_moldet_cfg.get("detection_batch_size", 0))
    except Exception:
        _render_dpi = DEFAULT_RENDER_DPI
        _detection_batch_size = 0

    detector = MolDetv2FTDetector()
    if not detector.is_available():
        logger.warning(
            "MolDetv2-FT unavailable, skipping image molecule extraction"
        )
        return []

    molscribe.load()

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
        skipped_pure_text = 0
        for page_idx in pages_to_process:
            page = doc.load_page(page_idx)

            # 跳过纯文本页：有大量原生文本且无嵌入图 → 不可能有分子结构
            native_text = page.get_text("text").strip()
            has_images = len(page.get_images()) > 0
            if len(native_text) > _TEXT_PAGE_CHAR_THRESHOLD and not has_images:
                skipped_pure_text += 1
                continue

            page_w_pts = page.rect.width
            page_h_pts = page.rect.height
            zoom = _render_dpi / _BASE_PDF_DPI
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)

            img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                pix.height, pix.width, pix.n
            )
            image = Image.fromarray(img_array)

            # 1. FT joint detection
            coref_result = detect_coref_via_ft_detector(image)

            # 2. For each mol bbox: crop, run MolScribe, save crop file
            scale_x = page_w_pts / pix.width if pix.width > 0 else 0
            scale_y = page_h_pts / pix.height if pix.height > 0 else 0
            for mol_idx, cb in enumerate(coref_result.bboxes):
                if cb.category_id != 1:
                    continue
                # normalized -> pixel
                px1 = int(round(cb.bbox[0] * pix.width))
                py1 = int(round(cb.bbox[1] * pix.height))
                px2 = int(round(cb.bbox[2] * pix.width))
                py2 = int(round(cb.bbox[3] * pix.height))
                if px2 <= px1 or py2 <= py1:
                    continue
                raw_crop = image.crop((px1, py1, px2, py2)).convert("L")
                # 预处理：白底黑线条 → 连通分量 → DBSCAN 取最大簇
                try:
                    from ..parsers.molecule.preprocess import preprocess_mol_image

                    crop = preprocess_mol_image(raw_crop)
                except Exception as pp_exc:
                    logger.debug("preprocess_mol_image failed: %s, using raw crop", pp_exc)
                    crop = raw_crop
                try:
                    scribe = molscribe.predict(crop)
                    smi = scribe.esmiles or ""
                except Exception as scribe_exc:
                    logger.warning("MolScribe failed on page %d: %s", page_idx, scribe_exc)
                    smi = ""
                # Save crop file under {project_root}/.mbforge/crops/{doc_id}/
                crop_filename = f"{doc_id}_page_{page_idx:04d}_mol_{mol_idx:04d}.png"
                crop_path = crop_dir / crop_filename
                try:
                    crop.save(crop_path)
                except Exception as save_exc:
                    logger.warning("Failed to save crop %s: %s", crop_path, save_exc)
                    crop_path = None
                # PDF-space bbox (lower-left origin)
                bbox_pdf = [
                    round(px1 * scale_x, 2),
                    round(page_h_pts - py2 * scale_y, 2),
                    round(px2 * scale_x, 2),
                    round(page_h_pts - py1 * scale_y, 2),
                ]
                results.append(
                    ExtractionResult(
                        esmiles=smi,
                        name="",
                        source="image",
                        moldet_conf=cb.score,
                        scribe_conf=scribe.scribe_conf if smi else 0.0,
                        composite_conf=cb.score * (scribe.scribe_conf if smi else 0.0),
                        bbox_pdf=bbox_pdf,
                        page_idx=page_idx,
                        context_text="",
                        mol_img_path=crop_path,
                        status="pending",
                        properties={},
                    )
                )
    finally:
        doc.close()

    logger.info(
        "Extracted %d molecule image candidates from %s (%d pure-text pages skipped, dpi=%s, batch=%d)",
        len(results), doc_id, skipped_pure_text, _render_dpi, _detection_batch_size,
    )
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
