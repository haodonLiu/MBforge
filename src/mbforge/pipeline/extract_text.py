"""PDF text extraction.

Uses PyMuPDF for native text extraction. For pages with <50 chars
(likely scanned), falls back to the OCR backend chain:

    MinerU → PaddleOCR → GLM-OCR → RapidOCR (local last resort)

OCR config is read from AppConfig.ocr (see backend ocr.chain.build_backends).
"""

from __future__ import annotations

import asyncio
import re
import time
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
        try:
            from ..utils.config import load_global_config

            upload_batch_size = int(load_global_config().ocr.upload_batch_size)
        except Exception:
            upload_batch_size = 1

        results: list[str] = [""] * len(page_indices)
        # Positions within ``page_indices`` that still need single-page OCR.
        # Starts as every position; the MinerU batch path narrows it to the
        # pages that came back empty, and a total batch failure falls through
        # to retrying all positions.
        pending_positions: list[int] = list(range(len(page_indices)))

        # batch_size > 1 时尝试 MinerU 批量路径
        if upload_batch_size > 1:
            try:
                from ..backends.ocr.mineru import MinerUBackend

                # MinerUBackend 期望 api_key；OCR config 用 mineru_api_key
                mineru_cfg = dict(ocr_config or {})
                if "api_key" not in mineru_cfg and "mineru_api_key" in mineru_cfg:
                    mineru_cfg["api_key"] = mineru_cfg["mineru_api_key"]
                mineru_backend = MinerUBackend(mineru_cfg)
                if mineru_backend.is_configured():
                    empty_after_batch: list[int] = []
                    for batch_start in range(0, len(page_indices), upload_batch_size):
                        batch_end = min(batch_start + upload_batch_size, len(page_indices))
                        batch_positions = list(range(batch_start, batch_end))
                        batch_images: list[bytes] = []
                        for pos in batch_positions:
                            page = doc.load_page(page_indices[pos])
                            zoom = 2.0
                            mat = fitz.Matrix(zoom, zoom)
                            pix = page.get_pixmap(matrix=mat, alpha=False)
                            batch_images.append(pix.tobytes("png"))
                        batch_results = mineru_backend.extract_text_batch(batch_images)
                        for offset, pos in enumerate(batch_positions):
                            if offset < len(batch_results):
                                results[pos] = batch_results[offset].text
                            if not results[pos].strip():
                                empty_after_batch.append(pos)
                    if not empty_after_batch:
                        return results
                    # Fall through to single-page retry for empty pages only
                    pending_positions = empty_after_batch
            except Exception as batch_exc:  # noqa: BLE001
                logger.warning("Batch OCR failed, falling back to single-page: %s", batch_exc)

        # 单页 fallback — per-page retry-with-backoff
        # OCR backends frequently time out or return empty under load; without
        # retries a single transient failure cascades into title=null,
        # doc_kind=image_only, no section headings. We retry up to 3 times with
        # exponential backoff (1s / 3s / 9s) and treat empty responses as a
        # failure signal so the loop actually re-attempts instead of giving up.
        max_attempts = 3
        for pos in pending_positions:
            page_idx = page_indices[pos]
            page = doc.load_page(page_idx)
            zoom = 2.0  # 144 DPI for OCR
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            image_bytes = pix.tobytes("png")
            text = ""
            for attempt in range(max_attempts):
                try:
                    result = extract_text_with_chain(image_bytes, ocr_config)
                    text = result.text or ""
                    if text.strip():
                        break
                except Exception as ocr_exc:  # noqa: BLE001
                    logger.warning(
                        "OCR attempt %d/%d failed for page %d: %s",
                        attempt + 1, max_attempts, page_idx + 1, ocr_exc,
                    )
                if attempt < max_attempts - 1:
                    time.sleep(1 * (3 ** attempt))  # 1s, 3s, 9s
            else:
                logger.warning(
                    "OCR gave up on page %d after %d attempts",
                    page_idx + 1, max_attempts,
                )
            results[pos] = text
        return results
    except Exception as e:  # noqa: BLE001
        logger.warning("OCR fallback failed: %s", e)
        return [""] * len(page_indices)


def _extract_title(text: str) -> str | None:
    """Extract a title from the first page text.

    Strategy:
    1. If a line starts with ``Title:`` / ``标题：`` / ``题目：``, take the rest.
    2. Otherwise pick the first substantive non-empty line, skipping:
       - PCT/WIPO bibliographic headers (``(NN) ...``)
       - Classification codes (``(51) ...``)
       - Long ALL-CAPS lines
    3. Cap at 200 chars.
    """
    if not text:
        return None

    # 1. explicit prefix wins
    for line in text.split("\n")[:30]:
        for prefix in ["Title:", "标题：", "题目："]:
            if line.strip().startswith(prefix):
                rest = line.strip()[len(prefix):].strip()
                if rest and 3 < len(rest) < 200:
                    return rest

    # 2. heuristic: skip bibliographic lines
    _biblio = re.compile(r"^\(\d{1,3}\)\s+")
    _all_caps = re.compile(r"^[A-Z][A-Z\s&\-,/]{4,}$")
    # Skip known patent header phrases
    _header_phrases = {
        "INTERNATIONAL APPLICATION PUBLISHED UNDER THE PATENT COOPERATION TREATY (PCT)",
        "INTERNATIONAL APPLICATION PUBLISHED UNDER THE PATENT COOPERATION TREATY",
    }
    candidate_with_caps = None  # remember the first ALL-CAPS line as fallback
    for line in text.split("\n")[:30]:
        s = line.strip()
        if not s:
            continue
        if not (3 < len(s) < 200):
            continue
        if s.isdigit():
            continue
        if _biblio.match(s):
            continue
        if s in _header_phrases:
            continue
        if _all_caps.match(s):
            # Patent titles are often ALL-CAPS — remember as fallback but keep
            # scanning for a more specific line.
            if candidate_with_caps is None:
                candidate_with_caps = s
            continue
        # Looks like a real title — return it
        return s
    return candidate_with_caps


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


async def extract_pdf_text_async(
    pdf_path: str, ocr_fallback: bool = True, ocr_config: dict | None = None
) -> ExtractedDocument:
    """Async wrapper that runs PyMuPDF/OCR extraction off the event loop."""
    return await asyncio.to_thread(extract_pdf_text, pdf_path, ocr_fallback, ocr_config)
