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


@pytest.fixture
def router():
    return OCRMethodRouter()


def _make_page(
    *,
    page_idx: int = 0,
    text_density: float = 100,
    is_scanned: bool = False,
    has_molecular_patterns: bool = False,
) -> PageClassification:
    return PageClassification(
        page_idx=page_idx,
        text_density=text_density,
        is_scanned=is_scanned,
        has_molecular_patterns=has_molecular_patterns,
    )


def _make_doc(
    *,
    text_density: float = 100,
    is_scanned: bool = False,
    has_molecular_patterns: bool = False,
    pages: list[PageClassification] | None = None,
) -> DocumentClassification:
    return DocumentClassification(
        text_density=text_density,
        is_scanned=is_scanned,
        has_molecular_patterns=has_molecular_patterns,
        pages=pages if pages is not None else [],
    )


class TestSelectMethod:
    """Test select_method routing logic."""

    def test_text_page(self, router):
        """Text page should use cheap API."""
        doc_class = _make_doc()
        page_class = _make_page()

        method = router.select_method(doc_class, page_class)
        assert method == OCRMethod.API_TEXT

    def test_scanned_with_molecules(self, router):
        """Scanned page with molecules should use expensive API."""
        doc_class = _make_doc(is_scanned=True, has_molecular_patterns=True)
        page_class = _make_page(is_scanned=True, has_molecular_patterns=True)

        method = router.select_method(doc_class, page_class)
        assert method == OCRMethod.API_FULL

    def test_scanned_no_molecules(self, router):
        """Scanned page without molecules should use cheap API."""
        doc_class = _make_doc(is_scanned=True)
        page_class = _make_page(is_scanned=True)

        method = router.select_method(doc_class, page_class)
        assert method == OCRMethod.API_TEXT

    def test_method_override_bypasses_selection(self, router):
        """Explicit method_override should bypass all auto-selection."""
        doc_class = _make_doc(is_scanned=True, has_molecular_patterns=True)
        page_class = _make_page(is_scanned=True, has_molecular_patterns=True)

        # Would normally select API_FULL, but override to LOCAL
        method = router.select_method(doc_class, page_class, method_override=OCRMethod.LOCAL)
        assert method == OCRMethod.LOCAL

    def test_method_override_vlm(self, router):
        """method_override=VLM should be honored regardless of page type."""
        doc_class = _make_doc()
        page_class = _make_page()

        method = router.select_method(doc_class, page_class, method_override=OCRMethod.VLM)
        assert method == OCRMethod.VLM


class TestEstimateCost:
    """Test estimate_cost for a single method."""

    def test_cost_estimation(self, router):
        """API_FULL 10 pages: cost 0.05 * 10 = 0.5."""
        estimate = router.estimate_cost(OCRMethod.API_FULL, 10)

        assert estimate.pages == 10
        assert estimate.estimated_cost_usd == pytest.approx(0.5)
        assert estimate.estimated_time_seconds == pytest.approx(20.0)

    def test_zero_pages(self, router):
        """Zero pages should yield zero cost and time."""
        estimate = router.estimate_cost(OCRMethod.API_FULL, 0)

        assert estimate.pages == 0
        assert estimate.estimated_cost_usd == 0.0
        assert estimate.estimated_time_seconds == 0.0

    def test_local_method_zero_cost(self, router):
        """LOCAL method has zero monetary cost."""
        estimate = router.estimate_cost(OCRMethod.LOCAL, 5)

        assert estimate.estimated_cost_usd == 0.0
        assert estimate.estimated_time_seconds == pytest.approx(150.0)


class TestEstimateTotalCost:
    """Test estimate_total_cost across a document."""

    def test_mixed_document(self, router):
        """Mixed scanned+text pages should sum per-page costs."""
        pages = [
            _make_page(page_idx=0, is_scanned=True, has_molecular_patterns=True),   # API_FULL
            _make_page(page_idx=1, is_scanned=True, has_molecular_patterns=False),  # API_TEXT
            _make_page(page_idx=2, is_scanned=False),                               # API_TEXT
        ]
        doc = _make_doc(pages=pages)

        estimate = router.estimate_total_cost(doc)

        # 0.05 + 0.01 + 0.01 = 0.07
        assert estimate.estimated_cost_usd == pytest.approx(0.07)
        # 2.0 + 1.0 + 1.0 = 4.0
        assert estimate.estimated_time_seconds == pytest.approx(4.0)
        assert estimate.pages == 3

    def test_empty_pages(self, router):
        """Document with no pages should return zero cost."""
        doc = _make_doc(pages=[])

        estimate = router.estimate_total_cost(doc)

        assert estimate.pages == 0
        assert estimate.estimated_cost_usd == 0.0
        assert estimate.estimated_time_seconds == 0.0
