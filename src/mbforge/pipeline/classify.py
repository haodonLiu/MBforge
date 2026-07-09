"""Document density classification — replaces old doc-type classifier.

Determines whether a document is primarily text, mixed (text + figures), or
image-only (scanned). This classification drives downstream stage branching:
- ``text_only`` → skip molecule image extraction
- ``mixed`` → run all stages including molecule image extraction
- ``image_only`` → run molecule extraction with high-DPI OCR
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..utils.logger import get_logger
from .extract_text import PageContent

logger = get_logger("mbforge.pipeline.classify")


@dataclass
class DensityClassification:
    """Per-document content density classification.

    text_only:  native text covers >80% of pages, OCR ran on <10%.
    mixed:    10–80% of pages needed OCR, OR a mixture of text and large figure blocks.
    image_only: >90% of pages needed OCR AND total native text < 1000 chars.
    """

    doc_kind: Literal["text_only", "mixed", "image_only"]
    page_count: int
    pages_needing_ocr: int
    avg_text_density: float


def classify_density(pages: list[PageContent]) -> DensityClassification:
    """Classify document content density based on per-page OCR metrics.

    Args:
        pages: List of PageContent objects from pdf text extraction.

    Returns:
        DensityClassification with doc_kind, counts, and average text density.
    """
    if not pages:
        return DensityClassification("image_only", 0, 0, 0.0)
    need_ocr = sum(1 for p in pages if p.needs_ocr)
    total_text = sum(len(p.text) for p in pages)
    if need_ocr / len(pages) > 0.9 and total_text < 1000:
        kind: Literal["text_only", "mixed", "image_only"] = "image_only"
    elif need_ocr / len(pages) > 0.1:
        kind = "mixed"
    else:
        kind = "text_only"
    total_density = max(sum(p.text_density for p in pages), 1e-9)
    avg_density = total_text / total_density
    return DensityClassification(kind, len(pages), need_ocr, avg_density)
