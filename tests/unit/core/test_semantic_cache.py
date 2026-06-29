"""Tests for core semantic cache."""

from mbforge.core.database import DatabaseManager
from mbforge.core.semantic_cache import (
    _query_hash,
    check_cache,
    invalidate_cache,
    store_cache,
)


class TestQueryHash:
    def test_deterministic(self):
        h1 = _query_hash("hello world")
        h2 = _query_hash("hello world")
        assert h1 == h2

    def test_case_insensitive(self):
        h1 = _query_hash("Hello World")
        h2 = _query_hash("hello world")
        assert h1 == h2

    def test_strips_whitespace(self):
        h1 = _query_hash("  hello world  ")
        h2 = _query_hash("hello world")
        assert h1 == h2

    def test_different_queries_different_hashes(self):
        h1 = _query_hash("query A")
        h2 = _query_hash("query B")
        assert h1 != h2


class TestSemanticCache:
    def _init_db(self, tmp_path):
        db = DatabaseManager(str(tmp_path))
        db.initialize()
        return db

    def test_cache_miss(self, tmp_path):
        self._init_db(tmp_path)
        result = check_cache("test query", str(tmp_path))
        assert result is None

    def test_store_and_retrieve(self, tmp_path):
        self._init_db(tmp_path)
        results = [{"text": "result 1", "score": 0.9}]
        store_cache("test query", str(tmp_path), results)
        cached = check_cache("test query", str(tmp_path))
        assert cached is not None
        assert cached[0]["text"] == "result 1"
        assert cached[0]["score"] == 0.9

    def test_invalidate_cache(self, tmp_path):
        self._init_db(tmp_path)
        store_cache("query", str(tmp_path), [{"x": 1}])
        assert check_cache("query", str(tmp_path)) is not None
        invalidate_cache(str(tmp_path))
        assert check_cache("query", str(tmp_path)) is None

    def test_case_insensitive_lookup(self, tmp_path):
        self._init_db(tmp_path)
        store_cache("Test Query", str(tmp_path), [{"x": 1}])
        cached = check_cache("test query", str(tmp_path))
        assert cached is not None

    def test_overwrite_on_reinsert(self, tmp_path):
        self._init_db(tmp_path)
        store_cache("q", str(tmp_path), [{"v": 1}])
        store_cache("q", str(tmp_path), [{"v": 2}])
        cached = check_cache("q", str(tmp_path))
        assert cached[0]["v"] == 2
