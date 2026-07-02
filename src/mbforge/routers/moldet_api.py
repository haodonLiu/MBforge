"""MolDet detection and extraction endpoints."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request

from ..backends import moldet
from ..parsers.molecule.coref_alt import (
    CorefResult as CorefResultData,
    coref_to_rust_dict,
    detect_coref_via_moldet_ocr,
    get_rapid_ocr,
)
from ..server_state import set_model_status
from ..utils.helpers import (
    ModelNotAvailableError,
    ValidationError,
    decode_base64_image,
)
from ..utils.logger import get_logger

logger = get_logger("mbforge.moldet_api_router")

router = APIRouter()


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _detect_from_pdf_sync(
    pdf_path: str, page_numbers: list[int], dpi: float
) -> dict[str, Any]:
    """Render PDF pages and detect molecule bboxes (single step)."""
    import fitz
    import numpy as np
    from PIL import Image

    pipeline = moldet.get_moldet()
    if pipeline is None or not pipeline.is_available():
        raise ModelNotAvailableError("MolDet pipeline not available")

    doc = fitz.open(pdf_path)
    try:
        all_results = []
        for page_num in page_numbers:
            page_index = int(page_num) - 1
            if page_index < 0 or page_index >= doc.page_count:
                continue
            page = doc.load_page(page_index)
            zoom = dpi / 72.0
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)

            img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                pix.height, pix.width, pix.n
            )
            image = Image.fromarray(img_array)

            boxes = pipeline.doc_detector.detect(image)
            all_results.append(
                {
                    "page_num": int(page_num),
                    "width": pix.width,
                    "height": pix.height,
                    "boxes": [
                        {"x1": x1, "y1": y1, "x2": x2, "y2": y2, "conf": conf}
                        for x1, y1, x2, y2, conf in boxes
                    ],
                    "count": len(boxes),
                }
            )
        return {"results": all_results, "total": len(all_results)}
    finally:
        doc.close()


def _enrich_results_with_coref(
    results: list,
    coref_result: CorefResultData,
) -> None:
    """Enrich ExtractionResult with coref context_text."""
    if not coref_result or not coref_result.corefs:
        return

    mol_idt_map: dict[int, list[str]] = {}
    for mol_idx, idt_idx in coref_result.corefs:
        if 0 <= idt_idx < len(coref_result.bboxes):
            text = coref_result.bboxes[idt_idx].text
            if text is None:
                continue
            mol_idt_map.setdefault(mol_idx, []).append(text)

    for i, result in enumerate(results):
        labels = mol_idt_map.get(i)
        if not labels:
            continue
        if len(labels) == 1:
            result.context_text = f"关联标号: {labels[0]}"
        else:
            result.context_text = f"关联 {len(labels)} 个标号: {', '.join(labels)}"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/detect-page")
async def detect_page(body: dict) -> dict[str, Any]:
    """Detect molecule bboxes. Supports image or PDF mode."""
    pdf_path = body.get("pdf_path", "")
    image_base64 = body.get("image_base64", "")

    if pdf_path:
        page_numbers = body.get("page_numbers", [1])
        dpi = body.get("dpi", 300.0)
        if not Path(pdf_path).exists():
            raise ValidationError(f"PDF not found: {pdf_path}")
        loop = asyncio.get_running_loop()
        results = await loop.run_in_executor(
            None, lambda: _detect_from_pdf_sync(pdf_path, page_numbers, dpi)
        )
        set_model_status("moldet", "ready")
        return results
    elif image_base64:
        image = decode_base64_image(image_base64)
        pipeline = moldet.get_moldet()
        if pipeline is None or not pipeline.is_available():
            raise ModelNotAvailableError("MolDet pipeline not available")
        loop = asyncio.get_running_loop()
        boxes = await loop.run_in_executor(
            None, lambda: pipeline.doc_detector.detect(image)
        )
        set_model_status("moldet", "ready")
        return {
            "boxes": [
                {"x1": x1, "y1": y1, "x2": x2, "y2": y2, "conf": conf}
                for x1, y1, x2, y2, conf in boxes
            ],
            "count": len(boxes),
        }
    else:
        raise ValidationError("image_base64 or pdf_path is required")


@router.post("/detect-batch")
async def detect_batch(body: dict) -> dict[str, Any]:
    """Batch detect molecule bboxes in multiple images."""
    image_base64_list = body.get("image_base64_list", [])
    if not isinstance(image_base64_list, list) or not image_base64_list:
        raise ValidationError("image_base64_list must be a non-empty list")
    images = [decode_base64_image(b64) for b64 in image_base64_list]
    pipeline = moldet.get_moldet()
    if pipeline is None or not pipeline.is_available():
        raise ModelNotAvailableError("MolDet pipeline not available")
    loop = asyncio.get_running_loop()
    batch_boxes = await loop.run_in_executor(
        None, lambda: pipeline.doc_detector.detect_batch(images)
    )
    set_model_status("moldet", "ready")
    return {
        "results": [
            {
                "page_index": i,
                "boxes": [
                    {"x1": x1, "y1": y1, "x2": x2, "y2": y2, "conf": conf}
                    for x1, y1, x2, y2, conf in boxes
                ],
                "count": len(boxes),
            }
            for i, boxes in enumerate(batch_boxes)
        ],
        "total": len(batch_boxes),
    }


@router.post("/extract-page")
async def extract_page(request: Request) -> dict[str, Any]:
    """Extract molecules from a page image with optional coref."""
    try:
        body = await request.json()
        image_base64 = body.get("image_base64", "")
        if not image_base64:
            raise ValidationError("image_base64 is required")
        page_idx = body.get("page_idx", 0)
        page_w_pts = body.get("page_w_pts", 595.0)
        page_h_pts = body.get("page_h_pts", 842.0)
        image_w = body.get("image_w", 0)
        image_h = body.get("image_h", 0)
        dpi = body.get("dpi", 300.0)
        use_coref = body.get("use_coref", True)

        if image_w == 0 or image_h == 0:
            raise ValidationError("image_w and image_h are required")

        image = decode_base64_image(image_base64)
        pipeline = moldet.get_moldet()
        if pipeline is None or not pipeline.is_available():
            raise ModelNotAvailableError("MolDet pipeline not available")

        loop = asyncio.get_running_loop()

        results = await loop.run_in_executor(
            None,
            lambda: pipeline.extract_page(
                image, page_idx, page_w_pts, page_h_pts, image_w, image_h, dpi
            ),
        )

        if use_coref and results:
            try:
                if (
                    pipeline.doc_detector is not None
                    and pipeline.doc_detector.is_available()
                ):
                    ocr_adapter = get_rapid_ocr()
                    coref_result = await loop.run_in_executor(
                        None,
                        lambda: detect_coref_via_moldet_ocr(
                            image,
                            pipeline.doc_detector,
                            ocr_adapter,
                            page_w_pts,
                            page_h_pts,
                        ),
                    )
                    _enrich_results_with_coref(results, coref_result)
            except Exception as e:
                logger.warning("[extract-page] Coref enrichment failed: %s", e)

        set_model_status("moldet", "ready")
        return {"results": [r.to_dict() for r in results], "count": len(results)}
    except (ValidationError, ModelNotAvailableError):
        raise
    except Exception as e:
        set_model_status("moldet", "error")
        raise ModelNotAvailableError(str(e)) from e


@router.post("/coref")
async def detect_coref(body: dict) -> dict[str, Any]:
    """Detect molecule-identifier coreference pairs."""
    image_base64 = body.get("image_base64", "")
    if not image_base64:
        raise ValidationError("image_base64 is required")

    image = decode_base64_image(image_base64)
    pipeline = moldet.get_moldet()
    if (
        pipeline is None
        or pipeline.doc_detector is None
        or not pipeline.doc_detector.is_available()
    ):
        raise ModelNotAvailableError("MolDet doc detector not available")

    ocr_adapter = get_rapid_ocr()
    loop = asyncio.get_running_loop()
    coref_result = await loop.run_in_executor(
        None,
        lambda: detect_coref_via_moldet_ocr(
            image,
            pipeline.doc_detector,
            ocr_adapter,
        ),
    )
    set_model_status("moldet_coref", "ready")
    return coref_to_rust_dict(coref_result)


@router.post("/coref_ft")
async def detect_coref_ft(body: dict) -> dict[str, Any]:
    """Detect coreference using FT joint detector."""
    from ..parsers.molecule.coref_alt import (
        detect_coref_via_ft_detector,
        coref_to_rust_dict as coref_to_rust_dict_ft,
    )

    image_base64 = body.get("image_base64", "")
    if not image_base64:
        raise ValidationError("image_base64 is required")

    image = decode_base64_image(image_base64)

    loop = asyncio.get_running_loop()
    coref_result = await loop.run_in_executor(
        None,
        lambda: detect_coref_via_ft_detector(image),
    )
    return coref_to_rust_dict_ft(coref_result)


@router.post("/extract-pdf-page")
async def extract_pdf_page(body: dict) -> dict[str, Any]:
    """Full pipeline: PDF render -> MolDet -> Coref -> MolScribe."""
    import numpy as np
    from PIL import Image

    from ..backends import molscribe

    pdf_path = body.get("pdf_path", "")
    if not pdf_path or not Path(pdf_path).exists():
        raise ValidationError("pdf_path is required and must exist")

    page_num = body.get("page", 1)
    dpi = body.get("dpi", 300.0)
    use_coref = body.get("use_coref", True)

    # 1. Render PDF page
    doc = fitz.open(pdf_path)
    try:
        page_index = int(page_num) - 1
        if page_index < 0 or page_index >= doc.page_count:
            raise ValidationError(f"Page {page_num} out of range (1-{doc.page_count})")
        page = doc.load_page(page_index)
        page_w_pts = page.rect.width
        page_h_pts = page.rect.height

        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
            pix.height, pix.width, pix.n
        )
        image = Image.fromarray(img_array)
        img_w, img_h = pix.width, pix.height
    finally:
        doc.close()

    # 2. MolDet detection
    pipeline = moldet.get_moldet()
    if pipeline is None or not pipeline.is_available():
        raise ModelNotAvailableError("MolDet pipeline not available")

    loop = asyncio.get_running_loop()

    boxes = await loop.run_in_executor(
        None,
        lambda: pipeline.doc_detector.detect(image),
    )

    scale_x = page_w_pts / img_w if img_w > 0 else 0
    scale_y = page_h_pts / img_h if img_h > 0 else 0

    # Coref pairing (optional)
    coref_result = None
    coref_dict: dict[str, Any] = {"bboxes": [], "corefs": []}
    if use_coref and boxes:
        try:
            ocr_adapter = get_rapid_ocr()
            coref_result = await loop.run_in_executor(
                None,
                lambda: detect_coref_via_moldet_ocr(
                    image,
                    pipeline.doc_detector,
                    ocr_adapter,
                    page_w_pts,
                    page_h_pts,
                ),
            )
            coref_dict = coref_to_rust_dict(coref_result)
        except Exception as e:
            logger.warning("[extract-pdf-page] Coref failed: %s", e)

    # 3. MolScribe recognition for each molecule
    await loop.run_in_executor(None, molscribe.load)

    async def _recognize_one(x1, y1, x2, y2):
        px1, py1 = max(0, int(x1)), max(0, int(y1))
        px2, py2 = min(img_w, int(x2)), min(img_h, int(y2))
        if px2 <= px1 or py2 <= py1:
            return ""
        crop = image.crop((px1, py1, px2, py2))
        crop_gray = crop.convert("L")
        sr = await loop.run_in_executor(None, lambda: molscribe.predict(crop_gray))
        return sr.esmiles if sr.esmiles else ""

    smiles_list = []
    for b in boxes:
        smi = await _recognize_one(*b[:4])
        smiles_list.append(smi)

    # 4. Coref label mapping
    coref_label_map: dict[int, str] = {}
    if coref_result:
        for mol_idx, idt_idx in coref_result.corefs:
            if 0 <= idt_idx < len(coref_result.bboxes):
                text = coref_result.bboxes[idt_idx].text
                if text:
                    coref_label_map[mol_idx] = text

    # 5. Assemble results
    molecules = []
    for i, (b, smi) in enumerate(zip(boxes, smiles_list)):
        x1, y1, x2, y2, conf = b
        label = coref_label_map.get(i, "")
        molecules.append(
            {
                "index": i,
                "bbox": {
                    "x1": round(x1 * scale_x, 2),
                    "y1": round(page_h_pts - y2 * scale_y, 2),
                    "x2": round(x2 * scale_x, 2),
                    "y2": round(page_h_pts - y1 * scale_y, 2),
                },
                "confidence": round(conf, 4),
                "smiles": smi,
                "scribe_conf": 0.0,
                "context_text": f"关联标号: {label}" if label else "",
            }
        )

    return {
        "page_num": int(page_num),
        "width": img_w,
        "height": img_h,
        "page_w_pts": page_w_pts,
        "page_h_pts": page_h_pts,
        "dpi": dpi,
        "molecules": molecules,
        "corefs": coref_dict.get("corefs", []),
        "bboxes": coref_dict.get("bboxes", []),
        "count": len(molecules),
    }
