"""Knowledge base search orchestrator.

Coordinates: embed query → Zvec hybrid search → semantic cache → rerank.
"""

from __future__ import annotations

import json
from typing import Any

from ..utils.logger import get_logger

logger = get_logger("mbforge.core.kb")


def search(
    query: str,
    project_root: str,
    top_k: int = 10,
    doc_id_filter: str | None = None,
    use_cache: bool = True,
) -> dict[str, Any]:
    """Hybrid knowledge base search.

    Pipeline: check cache → embed query → hybrid search (vector + FTS + RRF) → rerank → cache results.
    """
    from .semantic_cache import check_cache, store_cache

    # L1 cache check
    if use_cache:
        cached = check_cache(query, project_root)
        if cached is not None:
            return {"results": cached, "from_cache": True, "count": len(cached)}

    # Embed query
    try:
        from ..backends import qwen3_embed

        embeddings = qwen3_embed.embed([query])
        query_embedding = embeddings[0] if embeddings else []
    except Exception as e:
        logger.warning("Embedding failed, falling back to text search: %s", e)
        query_embedding = []

    # Search
    results: list[dict] = []

    try:
        from ..backends import zvec

        if query_embedding:
            # Hybrid search (vector + FTS with RRF fusion)
            hybrid = zvec.hybrid_search(query_embedding, query, top_k, doc_id_filter)
            results = hybrid.get("results", [])
        else:
            # Fallback: text-only search
            text_results = zvec.text_search(query, top_k, doc_id_filter)
            results = text_results.get("results", [])
    except Exception as e:
        logger.warning("Zvec search failed: %s", e)
        results = []

    # Rerank (optional)
    try:
        from ..backends import qwen3_rerank

        if results and len(results) > 1:
            passages = [r.get("text", "") for r in results]
            reranked = qwen3_rerank.rerank(query, passages)
            # Reorder results by rerank score
            ordered = []
            for idx, score in reranked:
                if idx < len(results):
                    results[idx]["rerank_score"] = score
                    ordered.append(results[idx])
            results = ordered[:top_k]
    except Exception as e:
        logger.debug("Rerank skipped: %s", e)

    # Cache results
    if use_cache and results:
        store_cache(query, project_root, results)

    return {"results": results, "from_cache": False, "count": len(results)}


def get_document_pages(project_root: str, doc_id: str, pages: list[int] | None = None) -> list[dict]:
    """Get page text content for a document."""
    from pathlib import Path

    pages_dir = Path(project_root) / "index" / "pages" / doc_id
    if not pages_dir.exists():
        return []

    result = []
    for page_file in sorted(pages_dir.glob("page_*.txt")):
        page_num = int(page_file.stem.split("_")[1])
        if pages is not None and page_num not in pages:
            continue
        text = page_file.read_text(encoding="utf-8")
        result.append({"page": page_num, "text": text})

    return result


def get_document_tree(project_root: str, doc_id: str) -> list[dict] | None:
    """Get the document structure tree."""
    from pathlib import Path

    tree_path = Path(project_root) / "index" / "doc_trees.json"
    if not tree_path.exists():
        return None
    try:
        data = json.loads(tree_path.read_text(encoding="utf-8"))
        return data.get(doc_id)
    except Exception:
        return None
