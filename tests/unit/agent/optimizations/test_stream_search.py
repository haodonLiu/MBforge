"""测试流式搜索."""

import shutil
import tempfile
from pathlib import Path

import pytest

from mbforge.agent.optimizations.stream_search import (
    StreamingKnowledgeBaseSearch,
    StreamingSearchConfig,
)
from mbforge.core.knowledge_base import KnowledgeBase


class FakeEmbedder:
    def embed(self, texts):
        return [[0.1] * 384 for _ in texts]


class FakeKB:
    """模拟 KnowledgeBase，返回固定结果。"""

    def __init__(self, n_results: int = 5):
        self._results = [
            {"id": f"doc{i}", "text": f"Chunk {i}", "metadata": {}, "distance": 0.1 * i}
            for i in range(n_results)
        ]

    def search(self, query, top_k=5, filter_dict=None):
        return self._results[:top_k]

    def search_streaming(self, query, top_k=5, filter_dict=None, yield_first=3):
        for i, r in enumerate(self._results[:top_k]):
            yield r


class TestStreamingSearch:
    def test_first_batch_yields_immediately(self):
        kb = FakeKB(n_results=5)
        streamer = StreamingKnowledgeBaseSearch(
            kb, StreamingSearchConfig(enabled=True, yield_first=2)
        )
        batches = list(streamer.stream("query", top_k=5))
        assert batches[0]["type"] == "first"
        assert len(batches[0]["results"]) == 2

    def test_complete_after_all_results(self):
        kb = FakeKB(n_results=3)
        streamer = StreamingKnowledgeBaseSearch(
            kb, StreamingSearchConfig(enabled=True, yield_first=2)
        )
        batches = list(streamer.stream("query", top_k=3))
        assert batches[-1]["type"] == "complete"
        assert batches[-1]["count"] == 3

    def test_disabled_falls_back_to_sync(self):
        kb = FakeKB(n_results=3)
        streamer = StreamingKnowledgeBaseSearch(
            kb, StreamingSearchConfig(enabled=False)
        )
        batches = list(streamer.stream("query", top_k=3))
        assert batches[0]["type"] == "complete"
        assert batches[0]["count"] == 3

    def test_incremental_results(self):
        kb = FakeKB(n_results=5)
        streamer = StreamingKnowledgeBaseSearch(
            kb, StreamingSearchConfig(enabled=True, yield_first=2)
        )
        batches = list(streamer.stream("query", top_k=5))
        incremental = [b for b in batches if b["type"] == "incremental"]
        assert len(incremental) == 3  # 5 total - 2 first = 3 incremental
