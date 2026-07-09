"""PDF text extraction.

Uses PyMuPDF for native text extraction. For pages with <50 chars
(likely scanned), falls back to the OCR backend chain:

    MinerU → PaddleOCR → GLM-OCR → RapidOCR (local last resort)

OCR config is read from AppConfig.ocr (see backend ocr.chain.build_backends).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import fitz

from ..utils.logger import get_logger

logger = get_logger("mbforge.pipeline.extract")


@dataclass
class TextSpan:
    """One text or image block from a PDF page with its bounding box."""

    text: str
    bbox: tuple[float, float, float, float]  # x0, y0, x1, y1 in PDF pts
    block_type: int = 0  # 0=text, 1=image


@dataclass
class PageContent:
    page_num: int  # 1-based
    text: str
    has_text: bool = True
    needs_ocr: bool = False
    ocr_dpi: int = 0
    text_density: float = 0.0
    text_spans: list[TextSpan] = field(default_factory=list)


@dataclass
class ExtractedDocument:
    raw_text: str
    page_count: int
    parser: str = "pymupdf"
    title: str | None = None
    pages: list[PageContent] = field(default_factory=list)


def extract_pdf_text(
    pdf_path: str, ocr_fallback: bool = True, ocr_config: dict | None = None
) -> ExtractedDocument:
    """Extract text from a PDF file.

    Strategy:
    1. PyMuPDF native text extraction (fast, works for most PDFs)
    2. For pages with <50 chars, run the OCR chain:
       MinerU → PaddleOCR → GLM-OCR → RapidOCR (local last resort)
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
                pages.append(
                    PageContent(page_num=i + 1, text="", has_text=False, needs_ocr=True)
                )
            else:
                span_blocks = page.get_text("dict")["blocks"]
                spans: list[TextSpan] = []
                for blk in span_blocks:
                    b = blk["bbox"]
                    if blk["type"] == 0:  # text block
                        text_content = "".join(
                            span.get("text", "")
                            for line in blk.get("lines", [])
                            for span in line.get("spans", [])
                        )
                        spans.append(TextSpan(text=text_content, bbox=b, block_type=0))
                    elif blk["type"] == 1:  # image block
                        spans.append(TextSpan(text="", bbox=b, block_type=1))
                pages.append(
                    PageContent(
                        page_num=i + 1,
                        text=text,
                        has_text=True,
                        needs_ocr=False,
                        text_spans=spans,
                    )
                )
                full_text_parts.append(text)

        # OCR fallback for scanned pages
        if pages_needing_ocr:
            ocr_texts = _ocr_pages(doc, pages_needing_ocr, ocr_config)
            for idx, ocr_text in zip(pages_needing_ocr, ocr_texts, strict=True):
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


def _ocr_pages(
    doc, page_indices: list[int], ocr_config: dict | None = None
) -> list[str]:
    """OCR scanned pages using the fallback chain.

    Priority: MinerU → PaddleOCR → GLM-OCR → RapidOCR (local last resort).
    When ``upload_batch_size > 1`` and MinerU is configured, pages are
    grouped and uploaded in a single batch to reduce round-trips.
    """
    try:
        from ..backends.ocr import extract_text_with_chain

        # 从 config 读取 OCR 上传 batch 大小（默认 1 = 逐页）
        upload_batch_size = 1
        try:
            from ..utils.config import load_global_config

            _ocr_cfg = (load_global_config().ocr or {})
            upload_batch_size = int(_ocr_cfg.get("upload_batch_size", 1))
        except Exception:
            pass

        results: list[str] = [""] * len(page_indices)

        # batch_size > 1 时尝试 MinerU 批量路径
        if upload_batch_size > 1:
            try:
                from ..backends.ocr.mineru import MinerUBackend

                mineru_backend = MinerUBackend(ocr_config)
                if mineru_backend.is_configured():
                    for batch_start in range(0, len(page_indices), upload_batch_size):
                        batch_end = min(batch_start + upload_batch_size, len(page_indices))
                        batch_indices = page_indices[batch_start:batch_end]
                        batch_images: list[bytes] = []
                        for idx in batch_indices:
                            page = doc.load_page(idx)
                            zoom = 2.0
                            mat = fitz.Matrix(zoom, zoom)
                            pix = page.get_pixmap(matrix=mat, alpha=False)
                            batch_images.append(pix.tobytes("png"))
                        batch_results = mineru_backend.extract_text_batch(batch_images)
                        for offset, idx in enumerate(range(batch_start, batch_end)):
                            if offset < len(batch_results):
                                results[idx] = batch_results[offset].text
                    return results
            except Exception as batch_exc:  # noqa: BLE001
                logger.warning("Batch OCR failed, falling back to single-page: %s", batch_exc)

        # 单页 fallback
        for idx, page_idx in enumerate(page_indices):
            page = doc.load_page(page_idx)
            zoom = 2.0  # 144 DPI for OCR
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            image_bytes = pix.tobytes("png")
            result = extract_text_with_chain(image_bytes, ocr_config)
            results[idx] = result.text
        return results
    except Exception as e:  # noqa: BLE001
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
                    line = line[len(prefix) :].strip()
            return line
    return None


HEADING_PATTERNS = re.compile(
    r"^(Abstract|Introduction|Background|Methods|Materials and Methods|"
    r"Results|Discussion|Conclusion|References|Acknowledgments|"
    r"Supporting Information|Supplementary|Appendix|"
    r"\d+\.\s+|FIGURES?|TABLES?)$",
    re.IGNORECASE,
)


def write_rough_markdown(pages: list[PageContent], output_path: str) -> None:
    """Write pages to a rough markdown with basic heading detection."""
    lines: list[str] = []
    for _i, page in enumerate(pages):
        lines.append(f"<!-- PAGE {page.page_num} -->")
        for para in page.text.split("\n"):
            stripped = para.strip()
            if not stripped:
                continue
            if HEADING_PATTERNS.match(stripped.split(".")[0].strip()):
                lines.append(f"## {stripped}")
            else:
                lines.append(stripped)
        lines.append("")
    Path(output_path).write_text("\n".join(lines), encoding="utf-8")
