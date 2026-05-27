"""Tests for PDF type classifier."""

from __future__ import annotations

import pytest
from pathlib import Path
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

    def test_classify_document_text_pdf(self, tmp_path):
        """Text-heavy PDF should be classified as text PDF."""
        classifier = PDFClassifier()
        pages = ["Page 1 content " * 50, "Page 2 content " * 50]
        result = classifier.classify_document_from_pages(pages)
        assert result.is_scanned is False
        assert result.text_density > 50

    def test_classify_document_scanned_pdf(self, tmp_path):
        """Image-heavy PDF should be classified as scanned."""
        classifier = PDFClassifier()
        pages = ["   ", "   ", "   "]
        result = classifier.classify_document_from_pages(pages)
        assert result.is_scanned is True
        assert result.text_density < 50
