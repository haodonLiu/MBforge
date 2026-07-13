"""PDF processing endpoints — classification + inspection stubs.

Full PDF parsing is implemented by `pipeline/extract_text.py` and
`routers/moldet_api.py:extract_pdf_page`. The endpoints here cover the
frontend's lightweight probes (classify, ocr-layout, figure-bboxes) used
by the queue UI before kicking off a full pipeline run.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.post("/classify")
async def classify_pdf(body: dict) -> dict:
    """Classify PDF type stub."""
    return {
        "pdf_type": "unknown",
        "confidence": 0.0,
        "page_count": 0,
        "pages_needing_ocr": [],
        "text_density_avg": 0.0,
        "has_complex_layout": False,
        "has_encoding_issues": False,
        "title": None,
    }


@router.post("/inspect")
async def inspect_pdf(body: dict) -> dict:
    """Inspect PDF stub."""
    return {
        "pdf_type": "unknown",
        "confidence": 0.0,
        "page_count": 0,
        "pages_needing_ocr": [],
        "text_density_avg": 0.0,
        "has_complex_layout": False,
        "has_encoding_issues": False,
        "title": None,
    }


@router.post("/confirm-ocr")
async def confirm_ocr(body: dict) -> dict:
    """Confirm OCR stub."""
    return {"success": True, "doc_id": body.get("docId", ""), "ocr_status": "pending", "task_id": ""}


@router.post("/extract-text")
async def extract_text(body: dict) -> dict:
    """Extract text stub."""
    return {
        "markdown": "",
        "page_count": 0,
        "pages_needing_ocr": [],
        "confidence": 0.0,
        "has_complex_layout": False,
        "has_encoding_issues": False,
    }


@router.post("/parse")
async def parse_pdf(body: dict) -> dict:
    """Full PDF parse stub."""
    return {
        "content": "",
        "classification": {
            "text_density": 0.0,
            "is_scanned": False,
            "has_molecular_patterns": False,
            "metadata_hints": None,
            "pages": [],
            "needs_confirmation": False,
        },
        "chunks": [],
        "esmiles": [],
        "activities": [],
        "parser": "stub",
        "page_count": 0,
        "images": [],
        "headings": [],
        "sections": [],
        "page_texts": [],
    }


@router.post("/process-document")
async def process_document(body: dict) -> dict:
    """Process document stub."""
    return {"success": True}


@router.post("/ocr-layout")
async def ocr_layout(body: dict) -> dict:
    """OCR layout stub."""
    return {"path": body.get("path", ""), "parser": "stub", "page_count": 0, "blocks": [], "from_cache": False}


@router.post("/figure-bboxes")
async def figure_bboxes(body: dict) -> list[dict]:
    """Return per-page figure bbox arrays for coref overlay projection.

    Real implementation lives in the pipeline layer (calls the figure-bbox
    detector). This stub preserves the API contract expected by the
    frontend (``usePdfViewer.ts`` → ``getFigureBboxes`` → ``PageFigureBboxes[]``)
    so the endpoint always parses against its declared return type even when
    the underlying detector is unavailable.

    Contract:
      - ``{"pdf_path": "<abs path>"}`` → list of ``{page_num, figures}``
        entries, one per PDF page. ``figures`` is the bbox array (empty when
        the page has no extractable figures).
      - Missing/unreadable PDF → ``[]``.
    """
    import fitz  # local import keeps the router importable without PyMuPDF

    pdf_path = body.get("pdf_path") or body.get("pdfPath") or ""
    if not pdf_path:
        return []
    try:
        with fitz.open(pdf_path) as doc:
            return [
                {"page_num": idx + 1, "figures": []}
                for idx in range(doc.page_count)
            ]
    except Exception:
        # File missing, encrypted, or unreadable — surface as empty result
        # rather than 500, so the frontend can fall back gracefully.
        return []
