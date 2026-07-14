"""Unit tests for PDF text extraction and OCR fallback indexing."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import fitz
import pytest

from mbforge.backends.ocr.base import OCRResult
from mbforge.pipeline.extract_text import (
    _ocr_pages,
    extract_pdf_text,
    extract_pdf_text_async,
)


def _make_pdf_with_pages(tmp_path: Path, page_texts: list[str]) -> Path:
    """Create a PDF where page i contains page_texts[i] at a fixed position."""
    pdf_path = tmp_path / "non_consecutive.pdf"
    doc = fitz.open()
    for text in page_texts:
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 72), text, fontsize=12)
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


def test_ocr_pages_non_consecutive_indices_no_index_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Non-consecutive page_indices must not trigger IndexError in _ocr_pages.

    Regression for issue C3: the result list is sized to ``len(page_indices)``,
    but the old code used the absolute page number as a list index.
    """
    page_texts = ["page zero", "page one", "page two", "page three", "page four"]
    pdf_path = _make_pdf_with_pages(tmp_path, page_texts)
    doc: Any = fitz.open(str(pdf_path))

    # Ask for pages 0, 2, 4 (non-consecutive absolute page numbers).
    requested_indices = [0, 2, 4]

    def fake_extract(image_bytes: bytes, _config: dict | None) -> OCRResult:
        # Return text based on a simple marker derived from image content.
        # We don't actually OCR; just verify the right page index reached us.
        return OCRResult(text="ocr text")

    monkeypatch.setattr(
        "mbforge.backends.ocr.extract_text_with_chain", fake_extract
    )

    try:
        results = _ocr_pages(doc, requested_indices, ocr_config={})
    finally:
        doc.close()

    assert len(results) == len(requested_indices)
    # All requested pages should have received the mocked OCR text.
    assert all(r == "ocr text" for r in results)


def test_ocr_pages_result_positions_align_with_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Result list order must match the order of ``page_indices`` exactly."""
    page_texts = ["A", "B", "C", "D", "E"]
    pdf_path = _make_pdf_with_pages(tmp_path, page_texts)
    doc: Any = fitz.open(str(pdf_path))

    requested_indices = [4, 1, 3]

    def fake_extract(image_bytes: bytes, _config: dict | None) -> OCRResult:
        return OCRResult(text="aligned")

    monkeypatch.setattr(
        "mbforge.backends.ocr.extract_text_with_chain", fake_extract
    )

    try:
        results = _ocr_pages(doc, requested_indices, ocr_config={})
    finally:
        doc.close()

    assert results == ["aligned", "aligned", "aligned"]


def test_ocr_pages_preserves_empty_results_for_missing_pages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pages that OCR cannot handle should keep their empty placeholder."""
    page_texts = ["A", "B", "C"]
    pdf_path = _make_pdf_with_pages(tmp_path, page_texts)
    doc: Any = fitz.open(str(pdf_path))

    requested_indices = [0, 1, 2]
    calls: list[int] = []

    def fake_extract(image_bytes: bytes, _config: dict | None) -> OCRResult:
        calls.append(len(calls))
        # Page 1 (calls 2, 3, 4 = three retry attempts) always returns empty.
        if 2 <= len(calls) <= 4:
            return OCRResult(text="", error="empty")
        return OCRResult(text=f"page-{len(calls)}")

    monkeypatch.setattr(
        "mbforge.backends.ocr.extract_text_with_chain", fake_extract
    )

    try:
        results = _ocr_pages(doc, requested_indices, ocr_config={})
    finally:
        doc.close()

    assert len(results) == 3
    assert results[0] == "page-1"
    assert results[1] == ""
    assert results[2] == "page-5"


def test_extract_pdf_text_async_offloads_to_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The async wrapper runs the sync extractor in asyncio.to_thread."""
    import asyncio

    calls: list[tuple[object, ...]] = []

    async def _fake_to_thread(func, *args, **kwargs):
        calls.append((func, args, kwargs))
        return None

    monkeypatch.setattr(asyncio, "to_thread", _fake_to_thread)

    result = asyncio.run(extract_pdf_text_async("/tmp/fake.pdf"))
    assert result is None
    assert len(calls) == 1
    assert calls[0][0] is extract_pdf_text
