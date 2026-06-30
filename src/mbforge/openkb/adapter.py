"""High-level OpenKB adapter facade."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from ..utils.logger import get_logger
from .compiler import WikiCompiler
from .indexer import PageIndexWrapper

logger = get_logger("mbforge.openkb.adapter")


class OpenKBAdapter:
    """Facade for OpenKB operations: index, compile, search."""

    def __init__(self, project_root: str):
        self._project_root = Path(project_root)
        self._openkb_dir = self._project_root / ".mbforge" / "openkb"
        self._wiki_dir = self._openkb_dir / "wiki"
        self._indexer: PageIndexWrapper | None = None
        self._compiler: WikiCompiler | None = None

    def _get_indexer(self) -> PageIndexWrapper:
        if self._indexer is None:
            self._indexer = PageIndexWrapper(str(self._openkb_dir))
        return self._indexer

    def _get_compiler(self) -> WikiCompiler:
        if self._compiler is None:
            self._compiler = WikiCompiler(str(self._wiki_dir))
        return self._compiler

    def index_document(self, pdf_path: str, doc_id: str = "") -> str:
        """Index a PDF via PageIndex tree. Returns the PageIndex doc ID."""
        indexer = self._get_indexer()
        return indexer.add_document(pdf_path, doc_id)

    def get_document(self, openkb_doc_id: str) -> Any:
        """Fetch the PageIndex document tree."""
        indexer = self._get_indexer()
        return indexer.get_document(openkb_doc_id)

    async def compile_wiki(
        self,
        doc_name: str,
        doc_id: str,
        page_count: int,
    ) -> None:
        """Compile wiki for an indexed document."""
        compiler = self._get_compiler()
        await compiler.compile_document(doc_name, doc_id, page_count)

    def search(self, query: str, top_k: int = 10) -> dict[str, Any]:
        """Search the wiki. Always called from sync context (via run_in_executor)."""
        from .query import search_wiki

        return asyncio.run(search_wiki(query, str(self._wiki_dir), top_k))
