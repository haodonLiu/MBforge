"""Knowledge base search orchestrator.

OpenKB wiki-based search via PageIndex tree indexing.
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
    """Search the knowledge base using OpenKB wiki."""
    from .semantic_cache import check_cache, store_cache

    if use_cache:
        cached = check_cache(query, project_root)
        if cached is not None:
            return {"results": cached, "from_cache": True, "count": len(cached)}

    try:
        from ..openkb.adapter import OpenKBAdapter

        adapter = OpenKBAdapter(project_root)
        result = adapter.search(query, top_k=top_k)
    except Exception as e:
        logger.warning("OpenKB search failed: %s", e)
        return {
            "results": [],
            "answer": "",
            "from_cache": False,
            "count": 0,
            "error": str(e),
        }

    results = result.get("results", [])
    answer = result.get("answer", "")

    if answer:
        results.insert(
            0,
            {
                "id": "openkb_answer",
                "text": answer,
                "metadata": {"type": "answer", "source": "openkb"},
                "score": 1.0,
            },
        )

    if doc_id_filter:
        results = [
            r
            for r in results
            if r.get("metadata", {}).get("doc_id") == doc_id_filter
            or r.get("id") == "openkb_answer"
        ]

    if use_cache and results:
        store_cache(query, project_root, results)

    return {
        "results": results[:top_k],
        "answer": answer,
        "from_cache": False,
        "count": len(results),
    }


def get_document_pages(
    project_root: str, doc_id: str, pages: list[int] | None = None
) -> list[dict]:
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
    """Get the document structure tree (from OpenKB wiki if available)."""
    from pathlib import Path

    # Try OpenKB wiki source files first
    wiki_dir = Path(project_root) / ".mbforge" / "openkb" / "wiki"
    if wiki_dir.exists():
        summary = wiki_dir / "summaries" / f"{doc_id}.md"
        if summary.exists():
            return [{"title": doc_id, "source": "openkb_wiki"}]

    # Fallback to legacy doc_trees.json
    tree_path = Path(project_root) / "index" / "doc_trees.json"
    if not tree_path.exists():
        return None
    try:
        data = json.loads(tree_path.read_text(encoding="utf-8"))
        return data.get(doc_id)
    except Exception:
        return None
