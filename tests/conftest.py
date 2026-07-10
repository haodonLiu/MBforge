"""Shared pytest fixtures for MBForge."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def tmp_library(tmp_path: Path) -> Path:
    """Return a temporary library root pre-created on disk."""
    lib = tmp_path / "library"
    lib.mkdir(parents=True, exist_ok=True)
    return lib


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    """Create a minimal 2-page text PDF for pipeline integration tests."""
    pdf_path = tmp_path / "sample.pdf"
    # Import inside fixture so tests that do not need PDFs avoid the import.
    import fitz

    doc = fitz.open()
    for i in range(2):
        page = doc.new_page(width=612, height=792)
        page.insert_text(
            (72, 72),
            f"Page {i + 1}. This document contains enough native text to avoid OCR fallback.",
            fontsize=12,
        )
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path
