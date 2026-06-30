"""Wiki compilation wrapper — delegates to OpenKB's compiler."""

from __future__ import annotations

from pathlib import Path

from ..utils.config import load_global_config
from ..utils.logger import get_logger

logger = get_logger("mbforge.openkb.compiler")


class WikiCompiler:
    """Compiles indexed documents into the OpenKB wiki."""

    def __init__(self, wiki_dir: str):
        self._wiki_dir = Path(wiki_dir)

    async def compile_document(
        self,
        doc_name: str,
        doc_id: str,
        page_count: int,
    ) -> None:
        """Compile a document into the wiki.

        Long docs (page_count >= threshold) use compile_long_doc;
        short docs use compile_short_doc.
        """
        cfg = load_global_config().llm

        try:
            from openkb.agent.compiler import compile_long_doc, compile_short_doc
        except ImportError as err:
            raise RuntimeError(
                "openkb package not installed. Run: uv add openkb"
            ) from err

        self._wiki_dir.mkdir(parents=True, exist_ok=True)
        summary_path = self._wiki_dir / "summaries" / f"{doc_id}.md"
        summary_path.parent.mkdir(parents=True, exist_ok=True)

        threshold = cfg.pageindex_threshold

        if page_count >= threshold:
            logger.info("Compiling long doc: %s (%d pages)", doc_name, page_count)
            await compile_long_doc(
                doc_name=doc_name,
                summary_path=str(summary_path),
                doc_id=doc_id,
                kb_dir=str(self._wiki_dir),
                model=cfg.model,
            )
        else:
            logger.info("Compiling short doc: %s (%d pages)", doc_name, page_count)
            await compile_short_doc(
                doc_name=doc_name,
                source_path=str(summary_path),
                kb_dir=str(self._wiki_dir),
                model=cfg.model,
            )

        logger.info("Wiki compiled for %s", doc_id)
