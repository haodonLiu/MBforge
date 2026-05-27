"""Tests for PDF type classifier."""

from __future__ import annotations

import pytest
from mbforge.parsers.pdf_classifier import (
    PDFClassifier,
    DocumentClassification,
    PageClassification,
)


class TestPDFClassifier:
    """Test PDFClassifier functionality."""

    def test_classify_page_text_rich(self):
        """Text-rich page should be classified as text page."""
        classifier = PDFClassifier()
        result = classifier.classify_page(
            page_text="This is a scientific paper about drug discovery. " * 20,
            page_idx=0,
        )
        assert result.is_scanned is False
        assert result.text_density > 200

    def test_classify_page_image_based(self):
        """Image-based page should be classified as scanned."""
        classifier = PDFClassifier()
        result = classifier.classify_page(
            page_text="   ",
            page_idx=0,
        )
        assert result.is_scanned is True
        assert result.text_density < 20

    def test_detect_molecular_patterns_smiles(self):
        """Should detect SMILES patterns in text."""
        classifier = PDFClassifier()
        text = "The compound CC(=O)Oc1ccccc1C(=O)O showed activity."
        result = classifier.classify_page(text, 0)
        assert result.has_molecular_patterns is True

    def test_detect_molecular_patterns_chemical_names(self):
        """Should detect chemical names in text."""
        classifier = PDFClassifier()
        text = "Aspirin (acetylsalicylic acid) is a common drug."
        result = classifier.classify_page(text, 0)
        assert result.has_molecular_patterns is True

    def test_classify_document_text_pdf(self):
        """Text-heavy PDF should be classified as text PDF."""
        classifier = PDFClassifier()
        pages = ["Page 1 content " * 50, "Page 2 content " * 50]
        result = classifier.classify_document_from_pages(pages)
        assert result.is_scanned is False
        assert result.text_density > 50

    def test_classify_document_scanned_pdf(self):
        """Image-heavy PDF should be classified as scanned."""
        classifier = PDFClassifier()
        pages = ["   ", "   ", "   "]
        result = classifier.classify_document_from_pages(pages)
        assert result.is_scanned is True
        assert result.text_density < 50

    def test_classify_document_empty_pages(self):
        """Empty pages list should return default classification."""
        classifier = PDFClassifier()
        result = classifier.classify_document_from_pages([])
        assert result.text_density == 0
        assert result.is_scanned is True
        assert result.has_molecular_patterns is False
        assert result.metadata_hints == {}
        assert result.pages == []
        assert result.needs_confirmation is False

    def test_analyze_metadata_filename_hint(self):
        """Metadata with molecular keyword in filename should produce hint."""
        classifier = PDFClassifier()
        metadata = {"filename": "drug_discovery_review.pdf"}
        hints = classifier._analyze_metadata(metadata)
        assert hints.get("filename_hint") is True
        assert "title_hint" not in hints

    def test_analyze_metadata_title_hint(self):
        """Metadata with molecular keyword in title should produce hint."""
        classifier = PDFClassifier()
        metadata = {"title": "Chemical Compound Analysis"}
        hints = classifier._analyze_metadata(metadata)
        assert hints.get("title_hint") is True
        assert "filename_hint" not in hints

    def test_analyze_metadata_no_hints(self):
        """Metadata without molecular keywords should produce empty hints."""
        classifier = PDFClassifier()
        metadata = {"filename": "report.pdf", "title": "Annual Report"}
        hints = classifier._analyze_metadata(metadata)
        assert hints == {}

    def test_analyze_metadata_empty(self):
        """Empty metadata should produce empty hints."""
        classifier = PDFClassifier()
        hints = classifier._analyze_metadata({})
        assert hints == {}

    def test_needs_confirmation_mixed_pages(self):
        """Mixed scanned/text pages should need confirmation."""
        classifier = PDFClassifier()
        pages = [
            PageClassification(page_idx=0, text_density=100, is_scanned=False, has_molecular_patterns=False),
            PageClassification(page_idx=1, text_density=5, is_scanned=True, has_molecular_patterns=False),
        ]
        assert classifier._needs_confirmation(pages) is True

    def test_needs_confirmation_molecular_patterns(self):
        """Pages with molecular patterns should need confirmation."""
        classifier = PDFClassifier()
        pages = [
            PageClassification(page_idx=0, text_density=100, is_scanned=False, has_molecular_patterns=True),
        ]
        assert classifier._needs_confirmation(pages) is True

    def test_needs_confirmation_all_scanned_no_molecules(self):
        """All scanned pages with no molecules should not need confirmation."""
        classifier = PDFClassifier()
        pages = [
            PageClassification(page_idx=0, text_density=5, is_scanned=True, has_molecular_patterns=False),
            PageClassification(page_idx=1, text_density=8, is_scanned=True, has_molecular_patterns=False),
        ]
        assert classifier._needs_confirmation(pages) is False

    def test_needs_confirmation_all_text_no_molecules(self):
        """All text pages with no molecules should not need confirmation."""
        classifier = PDFClassifier()
        pages = [
            PageClassification(page_idx=0, text_density=500, is_scanned=False, has_molecular_patterns=False),
            PageClassification(page_idx=1, text_density=600, is_scanned=False, has_molecular_patterns=False),
        ]
        assert classifier._needs_confirmation(pages) is False

    def test_non_molecular_text_no_patterns(self):
        """Plain English text without chemistry terms should have no molecular patterns."""
        classifier = PDFClassifier()
        text = (
            "The quick brown fox jumps over the lazy dog. "
            "This is a test of the classification system. "
            "No chemistry here at all."
        )
        result = classifier.classify_page(text, 0)
        assert result.has_molecular_patterns is False

    def test_smiles_pattern_no_false_positives(self):
        """Common English words should not match the SMILES pattern."""
        classifier = PDFClassifier()
        # These are common words that the old regex matched as false positives
        words = [
            "compound", "activity", "molecule", "reaction", "solution",
            "structure", "protein", "enzyme", "membrane", "receptor",
        ]
        for word in words:
            assert classifier.SMILES_PATTERN.search(word) is None, (
                f"Word '{word}' should not match SMILES pattern"
            )
