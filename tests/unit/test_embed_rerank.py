"""Embedding + Reranker 集成测试 — 验证模型加载和推理."""

import time

import pytest

from mbforge.utils.config import load_global_config


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def embedder():
    """加载 Embedding 模型（模块级共享，避免重复加载）."""
    from mbforge.models.embedding import create_embedder_from_config
    config = load_global_config()
    return create_embedder_from_config(config.embed)


@pytest.fixture(scope="module")
def reranker():
    """加载 Reranker 模型（模块级共享）."""
    from mbforge.models.rerank import create_reranker_from_config
    config = load_global_config()
    return create_reranker_from_config(config.rerank)


# ---------------------------------------------------------------------------
# Embedding 测试
# ---------------------------------------------------------------------------

class TestEmbedding:
    """Embedding 模型集成测试."""

    def test_embed_single(self, embedder):
        """单条文本嵌入返回正确维度."""
        vectors = embedder.embed(["阿司匹林是一种常用的解热镇痛药"])
        assert len(vectors) == 1
        assert len(vectors[0]) > 0  # 维度 > 0

    def test_embed_batch(self, embedder):
        """批量嵌入返回正确数量."""
        texts = ["IC50", "分子对接", "构效关系", "阿司匹林", "布洛芬"]
        vectors = embedder.embed(texts)
        assert len(vectors) == 5
        # 所有向量维度一致
        dims = {len(v) for v in vectors}
        assert len(dims) == 1

    def test_embed_empty_list(self, embedder):
        """空列表返回空结果."""
        vectors = embedder.embed([])
        assert vectors == []

    def test_embed_dimension(self, embedder):
        """验证嵌入维度符合预期."""
        vectors = embedder.embed(["test"])
        dim = len(vectors[0])
        # Qwen3-Embedding-0.6B 输出 1024 维
        assert dim >= 512  # 至少 512 维

    def test_embed_deterministic(self, embedder):
        """相同输入产生相同输出."""
        text = "乙酰水杨酸"
        v1 = embedder.embed([text])[0]
        v2 = embedder.embed([text])[0]
        assert v1 == v2

    def test_embed_different_texts_different_vectors(self, embedder):
        """不同文本产生不同向量."""
        v1 = embedder.embed(["阿司匹林"])[0]
        v2 = embedder.embed(["天气很好"])[0]
        # 至少有一个维度值不同
        assert v1 != v2

    def test_embed_performance(self, embedder):
        """批量嵌入性能测试."""
        texts = ["test"] * 20
        t0 = time.time()
        embedder.embed(texts)
        elapsed = time.time() - t0
        assert elapsed < 10.0  # 20 条应在 10 秒内完成


# ---------------------------------------------------------------------------
# Reranker 测试
# ---------------------------------------------------------------------------

class TestReranker:
    """Reranker 模型集成测试."""

    def test_rerank_basic(self, reranker):
        """基本排序功能."""
        query = "阿司匹林的合成方法"
        passages = [
            "乙酰水杨酸可以通过水杨酸与乙酸酐反应制得。",
            "今天天气很好，适合出去散步。",
            "阿司匹林化学名为2-乙酰氧基苯甲酸。",
        ]
        indexed = reranker.rerank(query, passages)
        assert len(indexed) == 3
        # 结果是 (index, score) 对
        for idx, score in indexed:
            assert 0 <= idx < 3
            assert 0.0 <= score <= 1.0

    def test_rerank_ordering(self, reranker):
        """相关文档排在不相关文档前面."""
        query = "阿司匹林的合成方法"
        passages = [
            "乙酰水杨酸可以通过水杨酸与乙酸酐反应制得。",
            "今天天气很好，适合出去散步。",
            "阿司匹林化学名为2-乙酰氧基苯甲酸，分子式C9H8O4。",
        ]
        indexed = reranker.rerank(query, passages)
        # 第一个结果的 score 应该最高
        best_idx = indexed[0][0]
        best_score = indexed[0][1]
        # 最相关的文档（合成方法 或 化学名）应排在天气前面
        weather_idx = 1  # "今天天气很好"
        weather_score = next(s for i, s in indexed if i == weather_idx)
        assert best_score > weather_score

    def test_rerank_empty(self, reranker):
        """空文档列表返回空结果."""
        indexed = reranker.rerank("test", [])
        assert indexed == []

    def test_rerank_single(self, reranker):
        """单个文档返回单个结果."""
        indexed = reranker.rerank("query", ["single passage"])
        assert len(indexed) == 1
        assert indexed[0][0] == 0

    def test_rerank_performance(self, reranker):
        """排序性能测试."""
        passages = [f"passage {i}" for i in range(10)]
        t0 = time.time()
        reranker.rerank("test query", passages)
        elapsed = time.time() - t0
        assert elapsed < 30.0  # 10 条应在 30 秒内完成


# ---------------------------------------------------------------------------
# Embedding + Reranker 联合测试
# ---------------------------------------------------------------------------

class TestEmbedRerankIntegration:
    """Embedding + Reranker 联合链路测试."""

    def test_embed_then_rerank(self, embedder, reranker):
        """先 Embedding 粗筛，再 Reranker 精排."""
        query = "阿司匹林的合成方法"
        docs = [
            "乙酰水杨酸可以通过水杨酸与乙酸酐反应制得，这是经典的酯化反应。",
            "今天天气很好，适合出去散步。",
            "阿司匹林化学名为2-乙酰氧基苯甲酸，分子式C9H8O4。",
            "分子对接是药物设计中的重要方法。",
            "水杨酸在硫酸催化下与乙酸酐发生酰化反应，生成乙酰水杨酸。",
        ]

        # 1. Embedding 粗筛
        import math
        def cosine(a, b):
            dot = sum(x * y for x, y in zip(a, b))
            na = math.sqrt(sum(x * x for x in a))
            nb = math.sqrt(sum(x * x for x in b))
            return dot / (na * nb) if na and nb else 0

        q_emb = embedder.embed([query])[0]
        doc_embs = embedder.embed(docs)
        sims = [(i, cosine(q_emb, e)) for i, e in enumerate(doc_embs)]
        sims.sort(key=lambda x: x[1], reverse=True)

        # 取 top 3
        top3_indices = [i for i, _ in sims[:3]]
        top3_docs = [docs[i] for i in top3_indices]

        # 2. Reranker 精排
        reranked = reranker.rerank(query, top3_docs)

        # 验证：天气不在 top 3 中
        weather_original_idx = 1
        assert weather_original_idx not in top3_indices

        # 验证：reranker 返回正确数量
        assert len(reranked) == 3

        # 验证：合成相关文档排在前面
        best_score = reranked[0][1]
        assert best_score > 0.5  # 最相关的应有较高分数
