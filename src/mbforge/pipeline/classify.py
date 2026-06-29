"""Document type classification.

Classifies documents as paper, patent, or report based on content heuristics.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..utils.logger import get_logger

logger = get_logger("mbforge.pipeline.classify")


@dataclass
class DocumentClassification:
    doc_type: str  # paper, patent, report, unknown
    confidence: float
    title: str | None = None


_PATENT_SIGNALS = [
    r"claims?\s*[:：]?\s*\d+",
    r"claim\s+\d+",
    r"patent\s+(application|number|no)",
    r"United States Patent",
    r"European Patent",
    r"WO\s*\d{4}/\d+",
    r"CN\s*\d+",
    r"abstract\s*[:：]",
    r"description\s*[:：]",
    r"field\s+of\s+(the\s+)?invention",
    r"background\s+(art|of\s+the\s+invention)",
    r"technical\s+field",
    r"B01|C07|A61|C12|G01",  # IPC class codes
]

_PAPER_SIGNALS = [
    r"abstract\s*[:：]",
    r"introduction\s*[:：]",
    r"references?\s*[:：]",
    r"bibliography",
    r"doi\s*[:：]?\s*10\.",
    r"journal\s+of",
    r"proceedings\s+of",
    r"et\s+al\.",
    r"fig(ure)?\.?\s*\d+",
    r"table\s+\d+",
    r"supplementary\s+(material|information|data)",
    r"acknowledgments?",
    r"conflict[s]?\s+of\s+interest",
]


def classify_document(text: str) -> DocumentClassification:
    """Classify a document based on its text content."""
    if not text or not text.strip():
        return DocumentClassification(doc_type="unknown", confidence=0.0)

    text_lower = text[:10000].lower()  # Only check first 10k chars

    patent_score = sum(1 for p in _PATENT_SIGNALS if re.search(p, text_lower, re.IGNORECASE))
    paper_score = sum(1 for p in _PAPER_SIGNALS if re.search(p, text_lower, re.IGNORECASE))

    total = patent_score + paper_score
    if total == 0:
        return DocumentClassification(doc_type="report", confidence=0.3)

    if patent_score > paper_score * 1.5:
        conf = min(0.95, patent_score / max(len(_PATENT_SIGNALS), 1))
        return DocumentClassification(doc_type="patent", confidence=conf)
    elif paper_score > patent_score * 1.5:
        conf = min(0.95, paper_score / max(len(_PAPER_SIGNALS), 1))
        return DocumentClassification(doc_type="paper", confidence=conf)
    else:
        # Mixed signals — pick the higher one with lower confidence
        if patent_score >= paper_score:
            return DocumentClassification(doc_type="patent", confidence=0.5)
        else:
            return DocumentClassification(doc_type="paper", confidence=0.5)
