"""High-level OpenKB adapter facade."""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import Any

from ..utils.helpers import FileAccessError, ValidationError
from ..utils.logger import get_logger
from .compiler import WikiCompiler
from .indexer import PageIndexWrapper
from .query import search_wiki

logger = get_logger("mbforge.openkb.adapter")

# Maximum markdown file size accepted for indexing (50 MB).
_MAX_MD_INDEX_BYTES = 50 * 1024 * 1024


class OpenKBAdapter:
    """Facade for OpenKB operations: index, compile, search."""

    def __init__(self, library_root: str) -> None:
        from ..core.layout import LibraryLayout

        self._library_root = Path(library_root)
        layout = LibraryLayout(library_root)
        self._openkb_dir = layout.openkb_dir
        # _global_openkb_dir is the storage dir for PageIndex documents.
        # Today it is co-located with the wiki dir; the pipeline-redesign
        # plan lifts it to a global config dir. Keep the alias here so
        # callers (e.g. index_markdown) bind to a stable name.
        self._global_openkb_dir = self._openkb_dir
        self._wiki_dir = layout.openkb_wiki_dir()
        self._indexer: PageIndexWrapper | None = None
        self._compiler: WikiCompiler | None = None

    def _get_indexer(self) -> PageIndexWrapper:
        if self._indexer is None:
            self._indexer = PageIndexWrapper(str(self._global_openkb_dir))
        return self._indexer

    def _get_compiler(self) -> WikiCompiler:
        if self._compiler is None:
            self._compiler = WikiCompiler(str(self._wiki_dir))
        return self._compiler

    def index_document(self, pdf_path: str, doc_id: str = "") -> str:
        """Index a PDF via PageIndex tree. Returns the PageIndex doc ID."""
        indexer = self._get_indexer()
        return indexer.add_document(pdf_path, doc_id)

    def index_markdown(self, md_path: str, doc_id: str = "") -> str:
        """Index a markdown file via PageIndex (MarkdownParser, level_based).

        Copies ``md_path`` into managed storage under the PageIndex documents
        dir and registers it via ``PageIndexWrapper.add_document``. The ``.md``
        extension triggers MarkdownParser → level_based strategy, which makes
        zero LLM calls.

        Args:
            md_path: Path to the markdown file.
            doc_id: Optional document ID. Defaults to the file stem.

        Returns:
            PageIndex document ID.
        """
        md_path_obj = Path(md_path)
        if not md_path_obj.exists():
            raise FileNotFoundError(f"Markdown file not found: {md_path}")
        if not md_path_obj.is_file():
            raise FileAccessError(f"Not a regular file: {md_path}")
        size = md_path_obj.stat().st_size
        if size > _MAX_MD_INDEX_BYTES:
            raise ValidationError(
                f"Markdown file too large ({size} bytes); max {_MAX_MD_INDEX_BYTES} bytes"
            )

        target_dir = self._global_openkb_dir / "documents"
        target_dir.mkdir(parents=True, exist_ok=True)
        md_name = f"{doc_id or md_path_obj.stem}.md"
        target_path = target_dir / md_name
        shutil.copy2(str(md_path_obj), str(target_path))

        # add_document resolves parser by extension (.md → MarkdownParser).
        return self._get_indexer().add_document(
            str(target_path), doc_id or md_path_obj.stem
        )

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
        return asyncio.run(search_wiki(query, str(self._wiki_dir), top_k))
