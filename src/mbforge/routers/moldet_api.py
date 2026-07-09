"""MolDetv2-FT main pipeline endpoints.

Rewritten 2026-07-08 to use the joint MolDetv2-FT detector (one model
inference: molecule bboxes + coref identifier bboxes) and the MolScribe
service for SMILES recognition. The legacy Doc/General detector pair
plus RapidOCR-based coref pairing has been removed.

Endpoints exposed (mounted by server.py under /api/v1/moldet):
- POST /coref_ft        - FT joint detection + coref pairing, image_base64
                          in, CorefResult dict out.
- POST /extract-pdf-page - Full PDF page pipeline: render -> FT detect ->
                          coref pair -> MolScribe -> SMILES+bbox+pairs.

Removed endpoints (return 410 Gone with a migration pointer):
- /detect-page, /detect-batch, /extract-page, /coref
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..parsers.molecule.coref_alt import (
    detect_coref_via_ft_detector,
    to_api_dict,
)
from ..utils.helpers import (
    ValidationError,
    decode_base64_image,
)
from ..utils.logger import get_logger

logger = get_logger("mbforge.moldet_api_router")

router = APIRouter()


# ---------------------------------------------------------------------------
# Removed endpoints - return 410 Gone with migration pointer
# ---------------------------------------------------------------------------

_REMOVED_PATHS: dict[str, str] = {
    "/detect-page": (
        "Removed. Use POST /api/v1/moldet/extract-pdf-page "
        "(full PDF pipeline with FT detector + MolScribe)."
    ),
    "/detect-batch": (
        "Removed. Loop /api/v1/moldet/extract-pdf-page per page, or use "
        "/api/v1/moldet/coref_ft per image."
    ),
    "/extract-page": (
        "Removed. Use POST /api/v1/moldet/extract-pdf-page with pdf_path, "
        "or /api/v1/moldet/coref_ft with image_base64."
    ),
    "/coref": (
        "Removed. Coref pairing is unified through /api/v1/moldet/coref_ft "
        "(FT model single-shot inference)."
    ),
}


def _gone_response(path: str) -> JSONResponse:
    return JSONResponse(
        status_code=410,
        content={
            "success": False,
            "error": _REMOVED_PATHS[path],
            "removed_at": "2026-07-08",
        },
    )


for _removed_path in _REMOVED_PATHS:

    @router.post(_removed_path, include_in_schema=False)
    async def _gone(request: Request, _p: str = _removed_path) -> JSONResponse:
        # include_in_schema=False keeps the 410 responses out of the OpenAPI
        # doc but the endpoint still resolves so frontends in the middle of
        # migration get a clear "this is gone" signal instead of 404.
        return _gone_response(_p)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _render_pdf_page_sync(
    pdf_path: str, page_num: int, dpi: float
) -> dict[str, Any]:
    """Render one PDF page to a PIL image and return its dims.

    Returns dict with keys: image (PIL.Image), img_w, img_h,
    page_w_pts, page_h_pts. Closes the fitz doc before returning.
    """
    import fitz
    import numpy as np
    from PIL import Image

    doc = fitz.open(pdf_path)
    try:
        page_index = int(page_num) - 1
        if page_index < 0 or page_index >= doc.page_count:
            raise ValidationError(
                f"Page {page_num} out of range (1-{doc.page_count})"
            )
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
        return {
            "image": image,
            "img_w": pix.width,
            "img_h": pix.height,
            "page_w_pts": page_w_pts,
            "page_h_pts": page_h_pts,
        }
    finally:
        doc.close()


def _molscribe_for_crop_sync(
    image, x1: int, y1: int, x2: int, y2: int
) -> str:
    """Crop a bbox from image and run MolScribe to SMILES. Empty on failure.

    Synchronous; intended to be wrapped in run_in_executor at the call site.
    """
    from ..backends import molscribe

    px1, py1 = max(0, int(x1)), max(0, int(y1))
    px2, py2 = min(image.width, int(x2)), min(image.height, int(y2))
    if px2 <= px1 or py2 <= py1:
        return ""
    crop = image.crop((px1, py1, px2, py2)).convert("L")
    try:
        result = molscribe.predict(crop)
        return result.esmiles if result.esmiles else ""
    except Exception as e:  # noqa: BLE001 - MolScribe is best-effort
        logger.warning(
            "MolScribe failed on crop (%s,%s,%s,%s): %s",
            px1, py1, px2, py2, e,
        )
        return ""


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/coref_ft")
async def detect_coref_ft(body: dict) -> dict[str, Any]:
    """FT model one-shot inference: joint detect molecules + coref ids, geometric pairing.

    Input: {"image_base64": "..."} (PIL image, base64 encoded)
    Output: {bboxes, corefs} standard format - bboxes (category_id,
    normalized bbox, score) + corefs (mol_idx -> idt_idx pairs).
    """
    image_base64 = body.get("image_base64", "")
    if not image_base64:
        raise ValidationError("image_base64 is required")

    image = decode_base64_image(image_base64)

    loop = asyncio.get_running_loop()
    coref_result = await loop.run_in_executor(
        None,
        lambda: detect_coref_via_ft_detector(image),
    )
    return to_api_dict(coref_result)


@router.post("/extract-pdf-page")
async def extract_pdf_page(body: dict) -> dict[str, Any]:
    """Full PDF page pipeline: render -> FT detect -> coref pair -> MolScribe.

    Input fields:
        pdf_path (str, required): absolute path to PDF file
        page (int, default 1): 1-based page number
        dpi (float, default 300): render DPI
        use_coref (bool, default True): whether to compute coref pairs
        mol_conf_threshold (float, default 0.3): molecule confidence threshold
        idt_conf_threshold (float, default 0.3): identifier confidence threshold

    Output:
        {
            "page_num", "width", "height", "page_w_pts", "page_h_pts", "dpi",
            "molecules": [
                {"index", "bbox": {x1, y1, x2, y2 in PDF points, lower-left origin},
                 "confidence", "smiles", "scribe_conf", "context_text"}
            ],
            "corefs": [[mol_idx, idt_idx], ...],  # raw int pairs
            "bboxes": [CorefBbox dicts],          # category_id = 1 or 3
            "count": N,
        }
    """
    pdf_path = body.get("pdf_path", "")
    if not pdf_path or not Path(pdf_path).exists():
        raise ValidationError("pdf_path is required and must exist")

    page_num = body.get("page", 1)
    dpi = body.get("dpi", 300.0)
    use_coref = body.get("use_coref", True)
    mol_conf_threshold = body.get("mol_conf_threshold", 0.3)
    idt_conf_threshold = body.get("idt_conf_threshold", 0.3)

    loop = asyncio.get_running_loop()

    # 1. Render PDF page (sync fitz call)
    page_info = await loop.run_in_executor(
        None, lambda: _render_pdf_page_sync(pdf_path, page_num, dpi)
    )
    image = page_info["image"]
    img_w = page_info["img_w"]
    img_h = page_info["img_h"]
    page_w_pts = page_info["page_w_pts"]
    page_h_pts = page_info["page_h_pts"]

    # 2. FT detection (always - needed for both mol detection and coref)
    def _ft_detect():
        return detect_coref_via_ft_detector(
            image,
            mol_conf_threshold=mol_conf_threshold,
            idt_conf_threshold=idt_conf_threshold,
        )

    coref_result = await loop.run_in_executor(None, _ft_detect)

    # Separate mol bboxes (pixel coords) from idt bboxes (text only)
    mol_boxes_px: list[tuple[int, int, int, int, float]] = []
    for cb in coref_result.bboxes:
        if cb.category_id == 1:
            x1 = int(round(cb.bbox[0] * img_w))
            y1 = int(round(cb.bbox[1] * img_h))
            x2 = int(round(cb.bbox[2] * img_w))
            y2 = int(round(cb.bbox[3] * img_h))
            mol_boxes_px.append((x1, y1, x2, y2, cb.score))
    api_dict = to_api_dict(coref_result)
    if not mol_boxes_px:
        logger.info(
            "FT detector found no molecules on page %s of %s",
            page_num, pdf_path,
        )
        return {
            "page_num": int(page_num),
            "width": img_w,
            "height": img_h,
            "page_w_pts": page_w_pts,
            "page_h_pts": page_h_pts,
            "dpi": dpi,
            "molecules": [],
            "corefs": api_dict["corefs"],
            "bboxes": api_dict["bboxes"],
            "count": 0,
        }

    # 3. MolScribe: one recognition per mol bbox
    from ..backends import molscribe

    await loop.run_in_executor(None, molscribe.load)

    async def _recognize_one(args):
        x1, y1, x2, y2 = args
        return await loop.run_in_executor(
            None, lambda: _molscribe_for_crop_sync(image, x1, y1, x2, y2)
        )

    smiles_list = await asyncio.gather(
        *[_recognize_one(b[:4]) for b in mol_boxes_px]
    )

    # 4. Build coref label map (mol_idx in coref_result.bboxes -> idt text)
    coref_label_map: dict[int, str] = {}
    if use_coref and coref_result.corefs:
        # coref_result.corefs = [(mol_idx_in_bboxes, idt_idx_in_bboxes), ...]
        # and the order of category_id=1 bboxes in coref_result.bboxes is
        # the same as mol_boxes_px (detect_coref_via_ft_detector appends in
        # detect() return order).
        for mol_idx_in_bboxes, idt_idx in coref_result.corefs:
            idt_text = coref_result.bboxes[idt_idx].text or ""
            if idt_text:
                coref_label_map[mol_idx_in_bboxes] = idt_text

    # 5. Assemble results - convert pixel -> PDF points (lower-left origin)
    scale_x = page_w_pts / img_w if img_w > 0 else 0
    scale_y = page_h_pts / img_h if img_h > 0 else 0

    molecules = []
    for i, ((px1, py1, px2, py2, conf), smi) in enumerate(
        zip(mol_boxes_px, smiles_list, strict=True)
    ):
        label = coref_label_map.get(i, "")
        molecules.append(
            {
                "index": i,
                "bbox": {
                    "x1": round(px1 * scale_x, 2),
                    "y1": round(page_h_pts - py2 * scale_y, 2),
                    "x2": round(px2 * scale_x, 2),
                    "y2": round(page_h_pts - py1 * scale_y, 2),
                },
                "confidence": round(conf, 4),
                "smiles": smi,
                "scribe_conf": 0.0,
                "context_text": f"coref label: {label}" if label else "",
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
        "corefs": api_dict["corefs"],
        "bboxes": api_dict["bboxes"],
        "count": len(molecules),
    }


@router.post("/extract-pdf")
async def extract_pdf_by_doc(body: dict) -> dict[str, Any]:
    """Same as /extract-pdf-page, but takes (project_root, doc_id, page)
    and resolves the absolute PDF path on the server side.

    Convenience for the frontend pdfService.ts (which works with the
    library's docId, not absolute paths). Reuses the same path-resolution
    logic as routers/coref.py::_resolve_pdf_path.
    """
    from .coref import _resolve_pdf_path

    project_root = body.get("project_root") or body.get("projectRoot") or ""
    doc_id = body.get("doc_id") or body.get("docId") or ""
    if not project_root or not doc_id:
        raise ValidationError("project_root and doc_id are required")

    pdf_path = _resolve_pdf_path(project_root, doc_id)
    if pdf_path is None:
        raise ValidationError(
            f"PDF not found for project_root={project_root} doc_id={doc_id}"
        )

    body_with_path = dict(body)
    body_with_path["pdf_path"] = str(pdf_path)
    return await extract_pdf_page(body_with_path)
