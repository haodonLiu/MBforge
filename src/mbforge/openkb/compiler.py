"""Wiki compilation wrapper — delegates to OpenKB's compiler."""

from __future__ import annotations

import os
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
        cfg = load_global_config().pageindex

        try:
            from openkb.agent.compiler import compile_long_doc, compile_short_doc
        except ImportError as err:
            raise RuntimeError(
                "openkb package not installed. Run: uv add openkb"
            ) from err

        self._wiki_dir.mkdir(parents=True, exist_ok=True)
        summary_path = self._wiki_dir / "summaries" / f"{doc_id}.md"
        summary_path.parent.mkdir(parents=True, exist_ok=True)

        threshold = cfg.threshold

        openkb_dir = Path(self._wiki_dir).parent
        kb_path = Path(self._wiki_dir)
        doc_md_path = openkb_dir / "documents" / f"{doc_id}.md"

        # OpenKB calls LiteLLM internally. Its environment receives only the
        # persisted PageIndex configuration, never a caller-provided override.
        os.environ["OPENAI_API_KEY"] = cfg.api_key
        os.environ["OPENAI_API_BASE"] = cfg.base_url
        litellm_model = f"openai/{cfg.model}"

        if page_count >= threshold:
            logger.info("Compiling long doc: %s (%d pages)", doc_name, page_count)
            # openkb 期望 summary_path 已存在；用 indexed markdown 内容预创建
            if not summary_path.exists() and doc_md_path.exists():
                summary_path.write_text(
                    doc_md_path.read_text(encoding="utf-8"), encoding="utf-8"
                )
            await compile_long_doc(
                doc_name=doc_name,
                summary_path=summary_path,  # Path object (openkb expects Path)
                doc_id=doc_id,
                kb_dir=kb_path,
                model=litellm_model,
            )
        else:
            logger.info("Compiling short doc: %s (%d pages)", doc_name, page_count)
            await compile_short_doc(
                doc_name=doc_name,
                source_path=doc_md_path,  # Path object (openkb expects Path)
                kb_dir=kb_path,
                model=litellm_model,
            )

        logger.info("Wiki compiled for %s", doc_id)
