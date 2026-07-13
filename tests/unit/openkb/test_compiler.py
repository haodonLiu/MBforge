from __future__ import annotations

import asyncio
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from mbforge.openkb import compiler as compiler_mod
from mbforge.openkb.compiler import WikiCompiler
from mbforge.utils.config import AppConfig, PageIndexConfig


@pytest.fixture
def _pageindex_config(monkeypatch: pytest.MonkeyPatch) -> None:
    config = AppConfig(
        pageindex=PageIndexConfig(
            api_key="pi-key",
            base_url="https://pi.example/v1",
            model="pi-model",
        )
    )
    monkeypatch.setattr(compiler_mod, "load_global_config", lambda: config)


@pytest.mark.asyncio
async def test_compile_short_doc_passes_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, _pageindex_config: None
) -> None:
    wiki = tmp_path / "wiki"
    docs = tmp_path / "documents"
    docs.mkdir(parents=True)
    (docs / "doc1.md").write_text("# Doc\nContent", encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", "legacy-key")
    monkeypatch.setenv("OPENAI_API_BASE", "https://legacy.example/v1")
    compiler = WikiCompiler(str(wiki))
    with patch("openkb.agent.compiler.compile_short_doc") as mock_compile:
        await compiler.compile_document("Doc", "doc1", page_count=1)
    assert mock_compile.called
    _, kwargs = mock_compile.call_args
    assert kwargs["api_key"] == "pi-key"
    assert kwargs["api_base"] == "https://pi.example/v1"
    assert kwargs["model"] == "openai/pi-model"
    assert os.environ["OPENAI_API_KEY"] == "legacy-key"
    assert os.environ["OPENAI_API_BASE"] == "https://legacy.example/v1"


@pytest.mark.asyncio
async def test_compile_long_doc_passes_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, _pageindex_config: None
) -> None:
    wiki = tmp_path / "wiki"
    docs = tmp_path / "documents"
    docs.mkdir(parents=True)
    (docs / "doc1.md").write_text("# Doc\nContent", encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", "legacy-key")
    monkeypatch.setenv("OPENAI_API_BASE", "https://legacy.example/v1")
    compiler = WikiCompiler(str(wiki))
    with patch("openkb.agent.compiler.compile_long_doc") as mock_compile:
        await compiler.compile_document("Doc", "doc1", page_count=100)
    assert mock_compile.called
    _, kwargs = mock_compile.call_args
    assert kwargs["api_key"] == "pi-key"
    assert kwargs["api_base"] == "https://pi.example/v1"
    assert kwargs["model"] == "openai/pi-model"
    assert os.environ["OPENAI_API_KEY"] == "legacy-key"
    assert os.environ["OPENAI_API_BASE"] == "https://legacy.example/v1"


def test_compiler_missing_openkb_raises(tmp_path: Path) -> None:
    compiler = WikiCompiler(str(tmp_path / "wiki"))
    original_import = __import__

    def _fake_import(name: str, *args, **kwargs):
        if name == "openkb" or name.startswith("openkb."):
            raise ImportError("no openkb")
        return original_import(name, *args, **kwargs)

    with (
        patch("builtins.__import__", _fake_import),
        pytest.raises(RuntimeError),
    ):
        asyncio.run(compiler.compile_document("Doc", "doc1", page_count=1))
