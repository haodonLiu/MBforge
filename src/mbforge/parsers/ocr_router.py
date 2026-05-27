"""OCR method selection router."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .pdf_classifier import DocumentClassification, PageClassification


class OCRMethod(Enum):
    """OCR method options."""

    API_FULL = "api_full"  # Expensive API (text + esmiles)
    API_TEXT = "api_text"  # Cheap API (text only)
    LOCAL = "local"  # Local pipeline
    VLM = "vlm"  # VLM fallback


@dataclass
class CostEstimate:
    """Cost estimation for OCR operation."""

    method: OCRMethod
    pages: int
    estimated_cost_usd: float
    estimated_time_seconds: float


# Cost per page (USD) and time (seconds)
PAGE_COST = {
    OCRMethod.API_FULL: 0.05,
    OCRMethod.API_TEXT: 0.01,
    OCRMethod.LOCAL: 0.0,
    OCRMethod.VLM: 0.02,
}

PAGE_TIME = {
    OCRMethod.API_FULL: 2.0,
    OCRMethod.API_TEXT: 1.0,
    OCRMethod.LOCAL: 30.0,
    OCRMethod.VLM: 5.0,
}


class OCRMethodRouter:
    """Select OCR method based on classification."""

    def select_method(
        self,
        doc_classification: DocumentClassification,
        page_classification: PageClassification,
        method_override: OCRMethod | None = None,
    ) -> OCRMethod:
        """Select appropriate OCR method for a page."""

        # 1. User override
        if method_override is not None:
            return method_override

        # 2. Auto-select based on content
        if page_classification.is_scanned:
            if page_classification.has_molecular_patterns:
                return OCRMethod.API_FULL
            else:
                return OCRMethod.API_TEXT
        else:
            # Text page - use cheap API
            return OCRMethod.API_TEXT

    def estimate_cost(
        self,
        method: OCRMethod,
        page_count: int,
    ) -> CostEstimate:
        """Estimate cost for OCR operation."""
        return CostEstimate(
            method=method,
            pages=page_count,
            estimated_cost_usd=PAGE_COST[method] * page_count,
            estimated_time_seconds=PAGE_TIME[method] * page_count,
        )

    def estimate_total_cost(
        self,
        doc_classification: DocumentClassification,
    ) -> CostEstimate:
        """Estimate total cost for entire document."""
        total_cost = 0.0
        total_time = 0.0

        for page in doc_classification.pages:
            method = self.select_method(doc_classification, page)
            total_cost += PAGE_COST[method]
            total_time += PAGE_TIME[method]

        return CostEstimate(
            method=OCRMethod.API_TEXT,  # Summary method
            pages=len(doc_classification.pages),
            estimated_cost_usd=total_cost,
            estimated_time_seconds=total_time,
        )
