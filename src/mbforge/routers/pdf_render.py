"""PDF rendering endpoints — page images for MoldDet."""

from __future__ import annotations

import base64
from pathlib import Path

from fastapi import APIRouter

from ..utils.logger import get_logger

logger = get_logger("mbforge.pdf_render_router")

router = APIRouter()


def _render_pages_sync(
    pdf_path: str,
    page_indices: list[int] | None = None,
    dpi: int = 200,
) -> list[dict]:
    """Render PDF pages to images (sync)."""
    import fitz  # PyMuPDF

    doc = fitz.open(pdf_path)
    pages_to_render = page_indices if page_indices else list(range(len(doc)))
    results = []
    for page_idx in pages_to_render:
        if page_idx < 0 or page_idx >= len(doc):
            continue
        page = doc[page_idx]
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat)
        img_bytes = pix.tobytes("png")
        img_b64 = base64.b64encode(img_bytes).decode("utf-8")
        results.append({
            "page": page_idx,
            "width": pix.width,
            "height": pix.height,
            "image_base64": img_b64,
        })
    doc.close()
    return results


@router.post("/render-pages")
async def render_pdf_pages(body: dict) -> dict:
    """Render PDF pages to base64 images."""
    pdf_path = body.get("pdf_path", "")
    page_indices = body.get("page_indices")
    dpi = body.get("dpi", 200)

    if not pdf_path:
        return {"success": False, "error": "pdf_path required"}

    if not Path(pdf_path).exists():
        return {"success": False, "error": f"PDF not found: {pdf_path}"}

    try:
        import asyncio

        loop = asyncio.get_running_loop()
        pages = await loop.run_in_executor(
            None, _render_pages_sync, pdf_path, page_indices, dpi
        )
        return {"success": True, "pages": pages}
    except Exception as e:
        logger.error("PDF render failed: %s", e)
        return {"success": False, "error": str(e)}


@router.post("/figure-bboxes")
async def figure_bboxes(body: dict) -> dict:
    """Extract figure bounding boxes from a PDF page."""
    pdf_path = body.get("pdf_path", "")
    page_idx = body.get("page_idx", 0)

    if not pdf_path:
        return {"success": False, "error": "pdf_path required"}

    try:
        import fitz

        doc = fitz.open(pdf_path)
        if page_idx >= len(doc):
            doc.close()
            return {"success": False, "error": "page_idx out of range"}

        page = doc[page_idx]
        images = page.get_images(full=True)
        bboxes = []
        for img in images:
            xref = img[0]
            rect = page.get_image_rects(xref)
            if rect:
                r = rect[0]
                bboxes.append({
                    "x0": r.x0,
                    "y0": r.y0,
                    "x1": r.x1,
                    "y1": r.y1,
                })
        doc.close()
        return {"success": True, "bboxes": bboxes}
    except Exception as e:
        logger.error("Figure bbox extraction failed: %s", e)
        return {"success": False, "error": str(e)}
