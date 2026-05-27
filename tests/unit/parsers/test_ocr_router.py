"""Tests for OCR method router."""

from __future__ import annotations

import pytest
from mbforge.parsers.ocr_router import (
    OCRMethodRouter,
    OCRMethod,
    CostEstimate,
)
from mbforge.parsers.pdf_classifier import (
    DocumentClassification,
    PageClassification,
)


class TestOCRMethodRouter:
    """Test OCRMethodRouter functionality."""

    def test_select_method_text_page(self):
        """Text page should use cheap API."""
        router = OCRMethodRouter()
        doc_class = DocumentClassification(
            text_density=100,
            is_scanned=False,
            has_molecular_patterns=False,
        )
        page_class = PageClassification(
            page_idx=0,
            text_density=100,
            is_scanned=False,
            has_molecular_patterns=False,
        )

        method = router.select_method(doc_class, page_class)
        assert method == OCRMethod.API_TEXT

    def test_select_method_scanned_with_molecules(self):
        """Scanned page with molecules should use expensive API."""
        router = OCRMethodRouter()
        doc_class = DocumentClassification(
            text_density=10,
            is_scanned=True,
            has_molecular_patterns=True,
        )
        page_class = PageClassification(
            page_idx=0,
            text_density=10,
            is_scanned=True,
            has_molecular_patterns=True,
        )

        method = router.select_method(doc_class, page_class)
        assert method == OCRMethod.API_FULL

    def test_select_method_scanned_no_molecules(self):
        """Scanned page without molecules should use cheap API."""
        router = OCRMethodRouter()
        doc_class = DocumentClassification(
            text_density=10,
            is_scanned=True,
            has_molecular_patterns=False,
        )
        page_class = PageClassification(
            page_idx=0,
            text_density=10,
            is_scanned=True,
            has_molecular_patterns=False,
        )

        method = router.select_method(doc_class, page_class)
        assert method == OCRMethod.API_TEXT

    def test_cost_estimation(self):
        """Should estimate cost correctly."""
        router = OCRMethodRouter()
        estimate = router.estimate_cost(OCRMethod.API_FULL, 10)

        assert estimate.pages == 10
        assert estimate.estimated_cost_usd > 0
        assert estimate.estimated_time_seconds > 0
