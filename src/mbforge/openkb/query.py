"""OpenKB query wrapper — run_query + source extraction."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..utils.config import load_global_config
from ..utils.logger import get_logger

logger = get_logger("mbforge.openkb.query")


async def search_wiki(
    query: str,
    wiki_dir: str,
    top_k: int = 10,
) -> dict[str, Any]:
    """Search the OpenKB wiki.

    Returns:
        {"results": [...], "answer": str, "count": int}
    """
    cfg = load_global_config().llm
    # OpenKB reads LiteLLM credentials from environment variables. Pass them
    # explicitly so the global process environment is never mutated.

    try:
        from openkb.agent.query import run_query
    except ImportError as err:
        raise RuntimeError("openkb package not installed. Run: uv add openkb") from err

    answer = await run_query(
        question=query,
        kb_dir=Path(wiki_dir),
        model=cfg.model,
        api_key=cfg.api_key or None,
        api_base=cfg.base_url or None,
    )

    sources = _extract_relevant_sources(query, wiki_dir, top_k)

    results = []
    for source in sources:
        results.append(
            {
                "id": source["id"],
                "text": source["text"],
                "metadata": {
                    "doc_id": source.get("doc_id", ""),
                    "page_start": source.get("page_start"),
                    "page_end": source.get("page_end"),
                    "section_title": source.get("title", ""),
                    "path": source.get("path", ""),
                    "type": "source",
                },
                "score": source.get("score", 0.5),
            }
        )

    return {
        "results": results[:top_k],
        "answer": answer or "",
        "count": len(results),
    }


def _extract_relevant_sources(
    query: str,
    wiki_dir: str,
    top_k: int,
) -> list[dict]:
    """Extract relevant source sections from wiki markdown files.

    Uses keyword matching over summaries and source pages.
    """
    wiki_path = Path(wiki_dir)
    sources: list[dict] = []

    # Search summaries/
    summaries_dir = wiki_path / "summaries"
    if summaries_dir.exists():
        sources.extend(_score_files(query, summaries_dir, "*.md"))

    # Search sources/ (may be .md or .json for long docs)
    sources_dir = wiki_path / "sources"
    if sources_dir.exists():
        sources.extend(_score_files(query, sources_dir, "*.md"))
        sources.extend(_score_files(query, sources_dir, "*.json"))

    # Search concepts/
    concepts_dir = wiki_path / "concepts"
    if concepts_dir.exists():
        sources.extend(_score_files(query, concepts_dir, "*.md"))

    sources.sort(key=lambda x: x["score"], reverse=True)
    return sources[:top_k]


def _score_files(query: str, directory: Path, pattern: str) -> list[dict]:
    """Score files in a directory by keyword overlap with the query."""
    query_terms = set(query.lower().split())
    scored: list[dict] = []

    for f in directory.glob(pattern):
        try:
            content = f.read_text(encoding="utf-8")
        except Exception as e:
            logger.debug("Failed to read %s: %s", f, e)
            continue

        content_lower = content.lower()
        score = sum(content_lower.count(term) for term in query_terms)
        if score <= 0:
            continue

        title = _extract_title(content)
        page_start, page_end = _extract_pages(content)

        scored.append(
            {
                "id": f.stem,
                "text": content[:2000],
                "doc_id": f.stem,
                "title": title,
                "page_start": page_start,
                "page_end": page_end,
                "path": str(f.relative_to(directory.parent)),
                "score": min(score / (len(query_terms) * 10), 1.0),
            }
        )

    return scored


def _extract_title(content: str) -> str:
    for line in content.split("\n")[:10]:
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def _extract_pages(content: str) -> tuple[int | None, int | None]:
    m = re.search(r"pages?\s*(\d+)(?:\s*[-–]\s*(\d+))?", content, re.IGNORECASE)
    if m:
        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) else start
        return start, end
    return None, None
