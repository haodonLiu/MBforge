from __future__ import annotations

from mbforge.core import semantic_cache as cache


def test_store_and_check_cache(in_memory_semantic_cache: str) -> None:
    root = in_memory_semantic_cache
    assert cache.check_cache("hello", root) is None
    cache.store_cache("hello", root, [{"id": 1}])
    assert cache.check_cache("hello", root) == [{"id": 1}]


def test_cache_is_case_and_whitespace_insensitive(in_memory_semantic_cache: str) -> None:
    root = in_memory_semantic_cache
    cache.store_cache("Hello World", root, [{"id": 2}])
    assert cache.check_cache("  hello world  ", root) == [{"id": 2}]


def test_cache_increments_hit_count(in_memory_semantic_cache: str) -> None:
    root = in_memory_semantic_cache
    cache.store_cache("q", root, [{"id": 3}])
    cache.check_cache("q", root)
    cache.check_cache("q", root)
    from mbforge.core.database import DatabaseManager

    db = DatabaseManager.get(root)
    with db.kb_conn() as conn:
        row = conn.execute(
            "SELECT hit_count FROM semantic_cache WHERE query_hash = ?",
            (cache._query_hash("q"),),
        ).fetchone()
    assert row["hit_count"] == 2


def test_invalidate_cache(in_memory_semantic_cache: str) -> None:
    root = in_memory_semantic_cache
    cache.store_cache("q", root, [{"id": 4}])
    cache.invalidate_cache(root)
    assert cache.check_cache("q", root) is None
