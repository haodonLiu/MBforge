"""PageIndexClient wrapper for document tree indexing."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ..utils.config import load_global_config
from ..utils.logger import get_logger

logger = get_logger("mbforge.openkb.indexer")


class PageIndexWrapper:
    """Lazy-initialized wrapper around PageIndexClient."""

    def __init__(self, storage_path: str):
        self._storage_path = Path(storage_path)
        self._client: Any = None
        self._collection: Any = None

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client

        cfg = load_global_config().llm

        try:
            from pageindex import PageIndexClient
        except ImportError as err:
            raise RuntimeError(
                "pageindex package not installed. Run: uv add pageindex"
            ) from err

        # LLM calls use LiteLLM model string (includes api_base for non-OpenAI)
        from .config import to_litellm_config

        litellm_cfg = to_litellm_config(cfg)

        # PAGEINDEX_API_KEY is separate from LLM api_key.
        # Only use cloud backend when PAGEINDEX_API_KEY is explicitly set.
        pageindex_api_key = os.environ.get("PAGEINDEX_API_KEY")

        # PageIndex internally calls litellm.completion() which reads
        # OPENAI_API_KEY and OPENAI_API_BASE from env. Ensure both are set
        # from our LLM config. The ?api_base= query-param approach causes
        # TCP connection timeout on some networks, so env vars are preferred.
        litellm_api_key = litellm_cfg.get("api_key", "")
        if litellm_api_key and not os.environ.get("OPENAI_API_KEY"):
            os.environ["OPENAI_API_KEY"] = litellm_api_key
        if cfg.base_url and not os.environ.get("OPENAI_API_BASE"):
            os.environ["OPENAI_API_BASE"] = cfg.base_url

        self._storage_path.mkdir(parents=True, exist_ok=True)
        self._client = PageIndexClient(
            api_key=pageindex_api_key,
            model=f"openai/{cfg.model}",
            storage_path=str(self._storage_path),
        )
        return self._client

    def _get_collection(self) -> Any:
        if self._collection is not None:
            return self._collection
        client = self._get_client()
        self._collection = client.collection()
        return self._collection

    def add_document(self, pdf_path: str, doc_id: str = "") -> str:
        """Index a PDF via PageIndex tree structure.

        Returns the PageIndex document ID.
        """
        col = self._get_collection()
        openkb_doc_id = col.add(pdf_path)
        logger.info("Indexed: %s → %s", pdf_path, openkb_doc_id)
        return openkb_doc_id

    def get_document(self, openkb_doc_id: str) -> Any:
        """Fetch document tree (with text) from the collection."""
        col = self._get_collection()
        return col.get_document(openkb_doc_id, include_text=True)

    def get_page_content(self, openkb_doc_id: str, pages: str) -> str:
        """Fetch specific page content. ``pages`` is a range string like "1-5,7"."""
        col = self._get_collection()
        return col.get_page_content(openkb_doc_id, pages)
