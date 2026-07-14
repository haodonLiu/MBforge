"""Unit tests for the OCR fallback chain and RapidOCR backend."""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import MagicMock

import pytest

from mbforge.backends.ocr import build_backends, extract_text_with_chain
from mbforge.backends.ocr.local import RapidOCRBackend
from mbforge.backends.ocr.mineru import MinerUBackend
from mbforge.backends.ocr.rapidocr_adapter import RapidOCRCropAdapter


def _make_mock_adapter(page_text: str = "mock page text", crop_texts: list[str] | None = None) -> MagicMock:
    """Return a mock RapidOCRCropAdapter with the expected methods."""
    mock = MagicMock(spec=RapidOCRCropAdapter)
    mock.readtext_page.return_value = page_text
    mock.readtext_batch.return_value = crop_texts or []
    return mock


def test_build_backends_rapidocr_only_when_no_cloud_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """If no cloud API keys are set, RapidOCR should be the only backend."""
    monkeypatch.setattr(
        RapidOCRCropAdapter,
        "instance",
        classmethod(lambda cls: _make_mock_adapter()),
        raising=False,
    )

    backends = build_backends({})
    names = [b.name for b in backends]
    assert names == ["rapidocr"]


def test_extract_text_with_chain_falls_back_to_rapidocr(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cloud backends without keys should fall through to RapidOCR."""
    mock_adapter = _make_mock_adapter(page_text="rapidocr text")
    monkeypatch.setattr(
        RapidOCRCropAdapter,
        "instance",
        classmethod(lambda cls: mock_adapter),
        raising=False,
    )
    _patch_image_open(monkeypatch)

    result = extract_text_with_chain(b"fake png bytes", {})
    assert result.text == "rapidocr text"
    assert result.error is None


def test_rapidocr_backend_extract_text_delegates_to_page_method(monkeypatch: pytest.MonkeyPatch) -> None:
    """RapidOCRBackend.extract_text must use the page-level read method."""
    mock_adapter = _make_mock_adapter(page_text="page level text")
    monkeypatch.setattr(
        RapidOCRCropAdapter,
        "instance",
        classmethod(lambda cls: mock_adapter),
        raising=False,
    )
    _patch_image_open(monkeypatch)

    backend = RapidOCRBackend({})
    result = backend.extract_text(b"fake png bytes")
    assert result.text == "page level text"
    assert mock_adapter.readtext_page.called
    assert not mock_adapter.readtext_batch.called


def _patch_image_open(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Patch PIL.Image.open so fake image bytes don't need to be valid PNG."""
    from PIL import Image

    mock_img = MagicMock(spec=Image.Image)
    mock_img.convert.return_value = mock_img
    monkeypatch.setattr(Image, "open", lambda _bytes: mock_img)
    return mock_img


def test_rapidocr_backend_is_configured_true_when_adapter_available(monkeypatch: pytest.MonkeyPatch) -> None:
    """is_configured returns True when the singleton builds successfully."""
    monkeypatch.setattr(
        RapidOCRCropAdapter,
        "instance",
        classmethod(lambda cls: _make_mock_adapter()),
        raising=False,
    )

    backend = RapidOCRBackend({})
    assert backend.is_configured() is True


def test_rapidocr_backend_is_configured_false_when_adapter_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """is_configured returns False when the singleton cannot initialize."""

    def _raise() -> Any:
        raise RuntimeError("rapidocr not installed")

    monkeypatch.setattr(
        RapidOCRCropAdapter,
        "instance",
        classmethod(lambda cls: _raise()),
        raising=False,
    )

    backend = RapidOCRBackend({})
    assert backend.is_configured() is False


def test_rapidocr_adapter_detect_use_dml_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """MBFORGE_RAPIDOCR_USE_DML env var should override auto-detection."""
    monkeypatch.setenv("MBFORGE_RAPIDOCR_USE_DML", "0")
    assert RapidOCRCropAdapter._detect_use_dml() is False

    monkeypatch.setenv("MBFORGE_RAPIDOCR_USE_DML", "1")
    assert RapidOCRCropAdapter._detect_use_dml() is True


def test_rapidocr_adapter_detect_use_dml_defaults_to_false(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without env override and with onnxruntime unavailable, DML defaults off."""
    monkeypatch.delenv("MBFORGE_RAPIDOCR_USE_DML", raising=False)
    monkeypatch.setattr(
        "builtins.__import__",
        lambda name, *args, **kwargs: (_ for _ in ()).throw(ImportError(name))
        if name == "onnxruntime"
        else __builtins__.__import__(name, *args, **kwargs),
    )
    assert RapidOCRCropAdapter._detect_use_dml() is False


def test_mineru_backend_init_and_extract_preserves_environ(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MinerU must not write OPENAI_API_KEY, OPENAI_API_BASE, or SSL_CERT_FILE."""
    monkeypatch.setenv("OPENAI_API_KEY", "legacy-key")
    monkeypatch.setenv("OPENAI_API_BASE", "https://legacy.example/v1")
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)

    backend = MinerUBackend({"api_key": "mineru-key"})

    # __init__ must not mutate env.
    assert os.environ.get("OPENAI_API_KEY") == "legacy-key"
    assert os.environ.get("OPENAI_API_BASE") == "https://legacy.example/v1"
    assert "SSL_CERT_FILE" not in os.environ

    # extract_text currently requires network; we only assert no env writes.
    # Patch the internal helpers so the method exits early.
    monkeypatch.setattr(backend, "_request_batch_urls", lambda _fn: ("", []))
    backend.extract_text(b"png")

    assert os.environ.get("OPENAI_API_KEY") == "legacy-key"
    assert os.environ.get("OPENAI_API_BASE") == "https://legacy.example/v1"
    assert "SSL_CERT_FILE" not in os.environ
