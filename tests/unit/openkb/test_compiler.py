from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest

from mbforge.openkb.compiler import WikiCompiler


@pytest.mark.asyncio
async def test_compile_short_doc_creates_summary(tmp_path: Path) -> None:
    wiki = tmp_path / "wiki"
    docs = tmp_path / "documents"
    docs.mkdir(parents=True)
    (docs / "doc1.md").write_text("# Doc\nContent", encoding="utf-8")
    compiler = WikiCompiler(str(wiki))
    with patch("openkb.agent.compiler.compile_short_doc") as mock_compile:
        await compiler.compile_document("Doc", "doc1", page_count=1)
    assert mock_compile.called


@pytest.mark.asyncio
async def test_compile_long_doc_uses_long_path(tmp_path: Path) -> None:
    wiki = tmp_path / "wiki"
    docs = tmp_path / "documents"
    docs.mkdir(parents=True)
    (docs / "doc1.md").write_text("# Doc\nContent", encoding="utf-8")
    compiler = WikiCompiler(str(wiki))
    with patch("openkb.agent.compiler.compile_long_doc") as mock_compile:
        await compiler.compile_document("Doc", "doc1", page_count=100)
    assert mock_compile.called


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
