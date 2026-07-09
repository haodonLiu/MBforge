"""Tests for pipeline document density classification."""

from __future__ import annotations

from mbforge.pipeline.classify import DensityClassification, classify_density
from mbforge.pipeline.extract_text import PageContent


class TestClassifyDensity:
    def test_empty_pages_returns_image_only(self):
        result = classify_density([])
        assert result == DensityClassification("image_only", 0, 0, 0.0)

    def test_text_only(self):
        pages = [
            PageContent(page_num=1, text="Hello world", text_density=11.0),
            PageContent(page_num=2, text="More text here", text_density=14.0),
        ]
        result = classify_density(pages)
        assert result.doc_kind == "text_only"
        assert result.page_count == 2
        assert result.pages_needing_ocr == 0

    def test_mixed(self):
        pages = [
            PageContent(page_num=1, text="Hello world", text_density=11.0),
            PageContent(
                page_num=2,
                text="",
                needs_ocr=True,
                has_text=False,
                text_density=0.0,
            ),
        ]
        result = classify_density(pages)
        assert result.doc_kind == "mixed"
        assert result.page_count == 2
        assert result.pages_needing_ocr == 1

    def test_image_only(self):
        pages = [
            PageContent(
                page_num=i,
                text="scan",
                needs_ocr=True,
                has_text=False,
                text_density=0.0,
            )
            for i in range(1, 11)
        ]
        result = classify_density(pages)
        assert result.doc_kind == "image_only"
        assert result.page_count == 10
        assert result.pages_needing_ocr == 10
