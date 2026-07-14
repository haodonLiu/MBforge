"""Semantic cache — L1 exact-hash query cache in SQLite.

Caches search results by query hash to avoid redundant embedding + search.
"""

from __future__ import annotations

import hashlib
import json

from mbforge.utils.logger import get_logger

logger = get_logger(__name__)


def _query_hash(query: str) -> str:
    return hashlib.sha256(query.strip().lower().encode()).hexdigest()


def check_cache(query: str, library_root: str) -> list[dict] | None:
    """Check if query results are cached. Returns None on miss."""
    from .database import DatabaseManager

    qh = _query_hash(query)
    db = DatabaseManager.get(library_root)
    try:
        with db.kb_conn() as conn:
            row = conn.execute(
                "SELECT results, hit_count FROM semantic_cache WHERE query_hash = ?",
                (qh,),
            ).fetchone()
            if row is None:
                return None
            # Update hit count
            conn.execute(
                "UPDATE semantic_cache SET hit_count = ?, last_hit = datetime('now') WHERE query_hash = ?",
                (row["hit_count"] + 1, qh),
            )
            return json.loads(row["results"])
    except Exception as e:
        logger.warning(
            "semantic_cache check_cache failed: %s (%s)", type(e).__name__, e
        )
        return None


def store_cache(query: str, library_root: str, results: list[dict]) -> None:
    """Store search results in cache."""
    from .database import DatabaseManager

    qh = _query_hash(query)
    db = DatabaseManager.get(library_root)
    try:
        with db.kb_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO semantic_cache (query_hash, query_text, results, library_root, hit_count) "
                "VALUES (?, ?, ?, ?, 0)",
                (qh, query, json.dumps(results, ensure_ascii=False), library_root),
            )
    except Exception as e:
        logger.warning(
            "semantic_cache store_cache failed: %s (%s)", type(e).__name__, e
        )


def invalidate_cache(library_root: str) -> None:
    """Clear all cached results for a project."""
    from .database import DatabaseManager

    db = DatabaseManager.get(library_root)
    try:
        with db.kb_conn() as conn:
            conn.execute("DELETE FROM semantic_cache")
    except Exception as e:
        logger.warning(
            "semantic_cache invalidate_cache failed: %s (%s)", type(e).__name__, e
        )
