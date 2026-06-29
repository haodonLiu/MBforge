"""PDF text extraction.

Uses PyMuPDF for native text extraction with OCR fallback for scanned pages.
Produces a markdown-like output with page separators.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..utils.logger import get_logger

logger = get_logger("mbforge.pipeline.extract")


@dataclass
class PageContent:
    page_num: int  # 1-based
    text: str
    has_text: bool = True
    needs_ocr: bool = False


@dataclass
class ExtractedDocument:
    raw_text: str
    page_count: int
    parser: str = "pymupdf"
    pages: list[PageContent] = field(default_factory=list)
    title: str | None = None


def extract_pdf_text(pdf_path: str, ocr_fallback: bool = True) -> ExtractedDocument:
    """Extract text from a PDF file.

    Strategy:
    1. PyMuPDF native text extraction (fast, works for most PDFs)
    2. For pages with <50 chars, try OCR via RapidOCR (scanned documents)
    """
    import fitz

    doc = fitz.open(pdf_path)
    try:
        pages: list[PageContent] = []
        full_text_parts: list[str] = []
        pages_needing_ocr: list[int] = []

        for i in range(doc.page_count):
            page = doc.load_page(i)
            text = page.get_text("text").strip()

            if len(text) < 50 and ocr_fallback:
                pages_needing_ocr.append(i)
                pages.append(PageContent(page_num=i + 1, text="", has_text=False, needs_ocr=True))
            else:
                pages.append(PageContent(page_num=i + 1, text=text, has_text=True))
                full_text_parts.append(text)

        # OCR fallback for scanned pages
        if pages_needing_ocr:
            ocr_texts = _ocr_pages(doc, pages_needing_ocr)
            for idx, ocr_text in zip(pages_needing_ocr, ocr_texts):
                pages[idx].text = ocr_text
                pages[idx].has_text = bool(ocr_text.strip())
                if ocr_text.strip():
                    full_text_parts.append(ocr_text)

        # Build full text with page separators
        full_text = "\n\n".join(full_text_parts)

        # Extract title from first page
        title = _extract_title(pages[0].text if pages else "")

        return ExtractedDocument(
            raw_text=full_text,
            page_count=doc.page_count,
            parser="pymupdf" + ("+ocr" if pages_needing_ocr else ""),
            pages=pages,
            title=title,
        )
    finally:
        doc.close()


def _ocr_pages(doc, page_indices: list[int]) -> list[str]:
    """OCR specific pages using RapidOCR."""
    try:
        from ..parsers.molecule.coref_alt import get_rapid_ocr
        import numpy as np

        ocr = get_rapid_ocr()
        results = []
        for idx in page_indices:
            page = doc.load_page(idx)
            zoom = 2.0  # 144 DPI for OCR
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)

            out = ocr._engine(arr)
            if out and out.txts:
                text = "\n".join(t for t in out.txts if t)
                results.append(text)
            else:
                results.append("")
        return results
    except Exception as e:
        logger.warning("OCR fallback failed: %s", e)
        return [""] * len(page_indices)


def _extract_title(text: str) -> str | None:
    """Extract a title from the first page text."""
    if not text:
        return None
    # First non-empty line that looks like a title (short, not a number)
    for line in text.split("\n")[:10]:
        line = line.strip()
        if line and len(line) > 3 and len(line) < 200 and not line.isdigit():
            # Remove common prefixes
            for prefix in ["Title:", "标题：", "题目："]:
                if line.startswith(prefix):
                    line = line[len(prefix):].strip()
            return line
    return None
