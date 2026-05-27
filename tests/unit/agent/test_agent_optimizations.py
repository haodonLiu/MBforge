"""端到端集成测试: 三层优化组合."""

import math
import shutil
import tempfile
from pathlib import Path

import pytest

from mbforge.agent.optimizations import (
    OptimizationConfig,
    SemanticCache,
    SemanticCacheConfig,
    SPSConfig,
    SpeculativeScheduler,
)


class FakeEmbedder:
    def embed(self, texts):
        import random

        random.seed(42)
        vecs = [[random.random() for _ in range(4)] for _ in texts]
        return [
            [x / math.sqrt(sum(y * y for y in v)) for x in v] for v in vecs
        ]


@pytest.fixture
def tmp_dir():
    d = tempfile.mkdtemp()
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


class TestOptimizationsCompose:
    def test_cache_and_sps_compose(self, tmp_dir):
        """验证缓存和 SPS 可以同时启用且不冲突."""
        cache = SemanticCache(tmp_dir, FakeEmbedder())
        sps = SpeculativeScheduler(config=SPSConfig(enabled=True))

        cache.store("aspirin mechanism", [{"id": "1", "text": "COX inhibition"}])

        sps.record_and_predict(
            "search_knowledge_base",
            {"query": "aspirin mechanism"},
            "COX inhibition result...",
        )

        assert cache.get_l1("aspirin mechanism") is not None
        preds = sps.record_and_predict("search_knowledge_base", {}, "")
        assert isinstance(preds, list)

    def test_optimization_config_serialization(self):
        cfg = OptimizationConfig()
        data = cfg.to_dict()
        restored = OptimizationConfig.from_dict(data)
        assert (
            restored.semantic_cache.similarity_threshold
            == cfg.semantic_cache.similarity_threshold
        )
        assert restored.sps.enabled == cfg.sps.enabled
        assert restored.streaming_search.yield_first == cfg.streaming_search.yield_first

    def test_optimization_config_from_dict_partial(self):
        """部分配置也能正确加载."""
        data = {"sps": {"enabled": False}}
        cfg = OptimizationConfig.from_dict(data)
        assert cfg.sps.enabled is False
        assert cfg.semantic_cache.enabled is True  # 默认值

    def test_cache_stats_after_operations(self, tmp_dir):
        cache = SemanticCache(tmp_dir, FakeEmbedder())
        for i in range(10):
            cache.store(f"query {i}", [{"id": str(i)}])
        for i in range(5):
            cache.get_l1(f"query {i}")
        stats = cache.stats()
        assert stats["entries"] == 10
        assert stats["total_hits"] >= 15  # 10 stores + 5 gets
