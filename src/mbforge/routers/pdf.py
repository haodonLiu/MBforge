"""PDF processing endpoints — classification + inspection stubs.

Full PDF parsing is implemented by `pipeline/extract_text.py` and
`routers/moldet_api.py:extract_pdf_page`. The endpoints here cover the
frontend's lightweight probes (classify, ocr-layout, figure-bboxes) used
by the queue UI before kicking off a full pipeline run.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ._path_utils import DocumentNotFoundError, InvalidPathError, resolve_pdf_path

router = APIRouter()


class FigureBbox(BaseModel):
    """Single embedded figure bbox in PDF point units."""

    xref: int
    bbox_pdf: tuple[float, float, float, float]
    width: float | None = None
    height: float | None = None


class PageFigureBboxes(BaseModel):
    """Per-page figure bbox collection returned by ``/figure-bboxes``."""

    page_num: int
    figures: list[FigureBbox]


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


@router.post("/figure-bboxes", response_model=list[PageFigureBboxes])
async def figure_bboxes(body: dict) -> list[PageFigureBboxes]:
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

    library_root = body.get("library_root") or body.get("libraryRoot") or ""
    doc_id = body.get("doc_id") or body.get("docId") or ""
    pdf_path = body.get("pdf_path") or body.get("pdfPath") or ""

    if library_root and doc_id:
        try:
            pdf_path = str(resolve_pdf_path(library_root, doc_id))
        except DocumentNotFoundError:
            # Missing but safely-resolved documents keep the existing
            # "empty result" contract so the frontend can fall back.
            return []
    elif pdf_path:
        # Direct absolute paths from the client are no longer trusted.
        raise InvalidPathError(
            "direct pdf_path is not allowed; provide library_root and doc_id"
        )
    else:
        raise InvalidPathError("library_root and doc_id are required")

    try:
        with fitz.open(pdf_path) as doc:
            return [
                PageFigureBboxes(page_num=idx + 1, figures=[])
                for idx in range(doc.page_count)
            ]
    except Exception:
        # File missing, encrypted, or unreadable — surface as empty result
        # rather than 500, so the frontend can fall back gracefully.
        return []
