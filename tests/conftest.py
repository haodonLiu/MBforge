"""Shared pytest fixtures for MBForge."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient


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


@pytest.fixture
def mock_llm_client() -> Any:
    """Return a fake LLM completion function."""

    def _client(model: str, prompt: str) -> str:
        # Minimal deterministic reorganize: return the prompt body after the system prompt.
        if "Document:" in prompt:
            return prompt.split("Document:", 1)[-1].split("Reorganized:")[0].strip()
        return "Summary line"

    return _client


@pytest.fixture
def app_client(tmp_library: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """FastAPI TestClient with global config pointing to a temp library."""
    from mbforge.app import app
    from mbforge.utils import config

    original_load = config.load_global_config

    def _load_temp():
        cfg = original_load()
        cfg.library_root = str(tmp_library)
        return cfg

    monkeypatch.setattr(config, "load_global_config", _load_temp)
    return TestClient(app)


@pytest.fixture
def in_memory_kb(tmp_library: Path) -> Any:
    """Initialize a DatabaseManager in a temp library."""
    from mbforge.core.database import DatabaseManager

    db = DatabaseManager.get(str(tmp_library))
    db.initialize()
    return db


@pytest.fixture
def in_memory_semantic_cache(tmp_library: Path) -> Any:
    """Initialize semantic cache tables in a temp library."""
    from mbforge.core.database import DatabaseManager

    db = DatabaseManager.get(str(tmp_library))
    db.initialize()
    return str(tmp_library)
