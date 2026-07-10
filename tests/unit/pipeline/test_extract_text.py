"""Tests for extract_text.py: TextSpan + text_spans on PageContent + write_rough_markdown."""

from __future__ import annotations

from pathlib import Path

from mbforge.pipeline.extract_text import (
    PageContent,
    TextSpan,
    _extract_title,
    write_rough_markdown,
)


def test_text_span_dataclass() -> None:
    span = TextSpan(text="hello", bbox=(0, 0, 100, 50))
    assert span.text == "hello"
    assert span.bbox == (0, 0, 100, 50)
    assert span.block_type == 0


def test_text_spans_on_page_content() -> None:
    pc = PageContent(page_num=1, text="test")
    assert hasattr(pc, "text_spans")
    assert pc.text_spans == []


def test_write_rough_markdown_creates_file(tmp_path: Path) -> None:
    pages = [
        PageContent(page_num=1, text="Abstract\nThis is a test."),
        PageContent(page_num=2, text="1. Introduction\nSome intro text."),
    ]
    out = tmp_path / "rough.md"
    write_rough_markdown(pages, str(out))
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert "---PAGE 1---" in content or "# " in content
    assert "Abstract" in content or "Introduction" in content


def test_extract_title_skips_pct_bibliographic_lines() -> None:
    text = """(12) INTERNATIONAL APPLICATION PUBLISHED UNDER THE PATENT COOPERATION TREATY (PCT)
(19) World Intellectual Property Organization International Bureau

PIPERIDYLUREA COMPOUNDS AND METHODS OF USE THEREOF

(51) International Patent Classification:
"""
    assert _extract_title(text) == "PIPERIDYLUREA COMPOUNDS AND METHODS OF USE THEREOF"


def test_extract_title_explicit_prefix_wins() -> None:
    text = """(12) header junk
Title: Real Title Here
(51) classification
"""
    assert _extract_title(text) == "Real Title Here"


def test_extract_title_chinese_prefix() -> None:
    text = """页眉杂项
标题：新型化合物专利
"""
    assert _extract_title(text) == "新型化合物专利"


def test_extract_title_empty_returns_none() -> None:
    assert _extract_title("") is None
    assert _extract_title("\n\n  \n") is None


def test_extract_title_only_bibliographic_returns_none() -> None:
    text = """(12) SOME HEADER
(19) SOMETHING ELSE
(51) CLASSIFICATIONS
"""
    assert _extract_title(text) is None


def test_ocr_pages_retries_on_empty(monkeypatch) -> None:
    """Empty OCR response is treated as failure → retries until success."""
    from unittest.mock import MagicMock
    from mbforge.pipeline import extract_text as extract_text_mod
    from mbforge.pipeline.extract_text import _ocr_pages

    # Sleep must not slow the test
    monkeypatch.setattr(extract_text_mod.time, "sleep", lambda _s: None)

    fake_doc = MagicMock()
    # Two pages — first returns empty twice then succeeds, second succeeds first try
    fake_page = MagicMock()
    fake_pix = MagicMock()
    fake_pix.tobytes.return_value = b"png-bytes"
    fake_pix.width = 100
    fake_pix.height = 100
    fake_page.get_pixmap.return_value = fake_pix
    fake_doc.load_page.return_value = fake_page

    call_log: list[int] = []

    class _FakeResult:
        def __init__(self, text: str):
            self.text = text

    def _fake_chain(_image_bytes: bytes, _cfg):
        call_log.append(len(call_log))
        # 1st page: attempts 0,1 return "" ; attempt 2 returns "ok"
        # 2nd page: attempt 0 returns "ok"
        idx = len(call_log) - 1
        if idx == 0 or idx == 1:
            return _FakeResult("")
        return _FakeResult("ok")

    # The OCR helper is imported lazily inside _ocr_pages — patch the source.
    monkeypatch.setattr(
        "mbforge.backends.ocr.extract_text_with_chain", _fake_chain
    )
    # Force single-page path (no batch)
    def _fake_load_global_config():
        return MagicMock(ocr={"upload_batch_size": 1})

    _fake_load_global_config.cache_clear = lambda: None
    monkeypatch.setattr(
        "mbforge.utils.config.load_global_config",
        _fake_load_global_config,
    )

    results = _ocr_pages(fake_doc, [0, 1], ocr_config=None)
    assert results == ["ok", "ok"]
    # page 0: 2 empty + 1 success = 3 calls; page 1: 1 success = 1 call → 4 total
    assert len(call_log) == 4


def test_ocr_pages_retries_on_exception(monkeypatch) -> None:
    """Exceptions also trigger retry."""
    from unittest.mock import MagicMock
    from mbforge.pipeline import extract_text as extract_text_mod
    from mbforge.pipeline.extract_text import _ocr_pages

    monkeypatch.setattr(extract_text_mod.time, "sleep", lambda _s: None)

    fake_doc = MagicMock()
    fake_page = MagicMock()
    fake_pix = MagicMock()
    fake_pix.tobytes.return_value = b"png-bytes"
    fake_page.get_pixmap.return_value = fake_pix
    fake_doc.load_page.return_value = fake_page

    call_count = {"n": 0}

    class _FakeResult:
        text = "recovered"

    def _fake_chain(_image_bytes: bytes, _cfg):
        call_count["n"] += 1
        if call_count["n"] < 3:
            raise RuntimeError("transient timeout")
        return _FakeResult()

    monkeypatch.setattr(
        "mbforge.backends.ocr.extract_text_with_chain", _fake_chain
    )

    def _fake_load_global_config():
        return MagicMock(ocr={"upload_batch_size": 1})

    _fake_load_global_config.cache_clear = lambda: None
    monkeypatch.setattr(
        "mbforge.utils.config.load_global_config",
        _fake_load_global_config,
    )

    results = _ocr_pages(fake_doc, [0], ocr_config=None)
    assert results == ["recovered"]
    assert call_count["n"] == 3


def test_ocr_pages_gives_up_after_max_attempts(monkeypatch) -> None:
    """After 3 failed attempts, page text stays empty (no crash)."""
    from unittest.mock import MagicMock
    from mbforge.pipeline import extract_text as extract_text_mod
    from mbforge.pipeline.extract_text import _ocr_pages

    monkeypatch.setattr(extract_text_mod.time, "sleep", lambda _s: None)

    fake_doc = MagicMock()
    fake_page = MagicMock()
    fake_pix = MagicMock()
    fake_pix.tobytes.return_value = b"png-bytes"
    fake_page.get_pixmap.return_value = fake_pix
    fake_doc.load_page.return_value = fake_page

    call_count = {"n": 0}

    class _FakeResult:
        def __init__(self, t=""):
            self.text = t

    def _fake_chain(_image_bytes: bytes, _cfg):
        call_count["n"] += 1
        return _FakeResult()  # always empty

    monkeypatch.setattr(
        "mbforge.backends.ocr.extract_text_with_chain", _fake_chain
    )

    def _fake_load_global_config():
        return MagicMock(ocr={"upload_batch_size": 1})

    _fake_load_global_config.cache_clear = lambda: None
    monkeypatch.setattr(
        "mbforge.utils.config.load_global_config",
        _fake_load_global_config,
    )

    results = _ocr_pages(fake_doc, [0], ocr_config=None)
    assert results == [""]
    assert call_count["n"] == 3  # exactly max attempts, not more


def test_ocr_pages_batch_empty_pages_fall_back(monkeypatch):
    """MinerU batch returning empty text for a page must trigger per-page fallback."""
    from unittest.mock import MagicMock
    from mbforge.pipeline import extract_text as extract_text_mod
    from mbforge.pipeline.extract_text import _ocr_pages

    monkeypatch.setattr(extract_text_mod.time, "sleep", lambda _s: None)

    fake_doc = MagicMock()
    fake_page = MagicMock()
    fake_pix = MagicMock()
    fake_pix.tobytes.return_value = b"png-bytes"
    fake_page.get_pixmap.return_value = fake_pix
    fake_doc.load_page.return_value = fake_page

    class _FakeBatchResult:
        def __init__(self, text: str):
            self.text = text

    class _FakeChainResult:
        def __init__(self, text: str):
            self.text = text

    batch_calls: list[list[bytes]] = []
    chain_calls: list[bytes] = []

    class _FakeMinerUBackend:
        def __init__(self, _cfg):
            pass

        def is_configured(self):
            return True

        def extract_text_batch(self, images):
            batch_calls.append(images)
            # Return text for 3 pages; middle one empty
            return [_FakeBatchResult("page1"), _FakeBatchResult(""), _FakeBatchResult("page3")]

    def _fake_chain(image_bytes: bytes, _cfg):
        chain_calls.append(image_bytes)
        return _FakeChainResult("recovered")

    def _fake_load_global_config():
        return MagicMock(ocr={"upload_batch_size": 3})

    _fake_load_global_config.cache_clear = lambda: None

    monkeypatch.setattr(
        "mbforge.backends.ocr.mineru.MinerUBackend", _FakeMinerUBackend
    )
    monkeypatch.setattr(
        "mbforge.backends.ocr.extract_text_with_chain", _fake_chain
    )
    monkeypatch.setattr(
        "mbforge.utils.config.load_global_config",
        _fake_load_global_config,
    )

    results = _ocr_pages(fake_doc, [0, 1, 2], ocr_config=None)
    assert results == ["page1", "recovered", "page3"]
    assert len(batch_calls) == 1
    assert len(chain_calls) == 1
