"""Embedding + Reranker 集成测试 — 验证模型加载和推理."""

import time
from unittest.mock import MagicMock

import pytest

from mbforge.backends import qwen3_embed, qwen3_rerank


# ---------------------------------------------------------------------------
# Embedding 测试
# ---------------------------------------------------------------------------

class TestEmbedding:
    """Embedding 模型集成测试."""

    def test_embed_single(self):
        """单条文本嵌入返回正确维度."""
        vectors = qwen3_embed.embed(["阿司匹林是一种常用的解热镇痛药"])
        assert len(vectors) == 1
        assert len(vectors[0]) > 0

    def test_embed_batch(self):
        """批量嵌入返回正确数量."""
        texts = ["IC50", "分子对接", "构效关系", "阿司匹林", "布洛芬"]
        vectors = qwen3_embed.embed(texts)
        assert len(vectors) == 5
        dims = {len(v) for v in vectors}
        assert len(dims) == 1

    def test_embed_empty_list(self):
        """空列表返回空结果."""
        vectors = qwen3_embed.embed([])
        assert vectors == []

    def test_embed_dimension(self):
        """验证嵌入维度符合预期."""
        vectors = qwen3_embed.embed(["test"])
        dim = len(vectors[0])
        assert dim >= 512

    def test_embed_deterministic(self):
        """相同输入产生相同输出."""
        text = "乙酰水杨酸"
        v1 = qwen3_embed.embed([text])[0]
        v2 = qwen3_embed.embed([text])[0]
        assert v1 == v2

    def test_embed_different_texts_different_vectors(self):
        """不同文本产生不同向量."""
        v1 = qwen3_embed.embed(["阿司匹林"])[0]
        v2 = qwen3_embed.embed(["天气很好"])[0]
        assert v1 != v2

    def test_embed_performance(self):
        """批量嵌入性能测试."""
        texts = ["test"] * 20
        t0 = time.time()
        qwen3_embed.embed(texts)
        elapsed = time.time() - t0
        assert elapsed < 10.0


# ---------------------------------------------------------------------------
# Reranker 测试
# ---------------------------------------------------------------------------

class TestReranker:
    """Reranker 模型集成测试."""

    def test_rerank_basic(self):
        """基本排序功能."""
        query = "阿司匹林的合成方法"
        passages = [
            "乙酰水杨酸可以通过水杨酸与乙酸酐反应制得。",
            "今天天气很好，适合出去散步。",
            "阿司匹林化学名为2-乙酰氧基苯甲酸。",
        ]
        indexed = qwen3_rerank.rerank(query, passages)
        assert len(indexed) == 3
        for idx, score in indexed:
            assert 0 <= idx < 3
            assert 0.0 <= score <= 1.0

    def test_rerank_ordering(self):
        """相关文档排在不相关文档前面."""
        query = "阿司匹林的合成方法"
        passages = [
            "乙酰水杨酸可以通过水杨酸与乙酸酐反应制得。",
            "今天天气很好，适合出去散步。",
            "阿司匹林化学名为2-乙酰氧基苯甲酸，分子式C9H8O4。",
        ]
        indexed = qwen3_rerank.rerank(query, passages)
        best_score = indexed[0][1]
        weather_score = next(s for i, s in indexed if i == 1)
        assert best_score > weather_score

    def test_rerank_empty(self):
        """空文档列表返回空结果."""
        indexed = qwen3_rerank.rerank("test", [])
        assert indexed == []

    def test_rerank_single(self):
        """单个文档返回单个结果."""
        indexed = qwen3_rerank.rerank("query", ["single passage"])
        assert len(indexed) == 1
        assert indexed[0][0] == 0

    def test_rerank_performance(self):
        """排序性能测试."""
        passages = [f"passage {i}" for i in range(10)]
        t0 = time.time()
        qwen3_rerank.rerank("test query", passages)
        elapsed = time.time() - t0
        assert elapsed < 30.0


# ---------------------------------------------------------------------------
# Embedding + Reranker 联合测试
# ---------------------------------------------------------------------------

class TestEmbedRerankIntegration:
    """Embedding + Reranker 联合链路测试."""

    def test_embed_then_rerank(self):
        """先 Embedding 粗筛，再 Reranker 精排."""
        query = "阿司匹林的合成方法"
        docs = [
            "乙酰水杨酸可以通过水杨酸与乙酸酐反应制得，这是经典的酯化反应。",
            "今天天气很好，适合出去散步。",
            "阿司匹林化学名为2-乙酰氧基苯甲酸，分子式C9H8O4。",
            "分子对接是药物设计中的重要方法。",
            "水杨酸在硫酸催化下与乙酸酐发生酰化反应，生成乙酰水杨酸。",
        ]

        import math
        def cosine(a, b):
            dot = sum(x * y for x, y in zip(a, b))
            na = math.sqrt(sum(x * x for x in a))
            nb = math.sqrt(sum(x * x for x in b))
            return dot / (na * nb) if na and nb else 0

        q_emb = qwen3_embed.embed([query])[0]
        doc_embs = qwen3_embed.embed(docs)
        sims = [(i, cosine(q_emb, e)) for i, e in enumerate(doc_embs)]
        sims.sort(key=lambda x: x[1], reverse=True)

        top3_indices = [i for i, _ in sims[:3]]
        top3_docs = [docs[i] for i in top3_indices]
        reranked = qwen3_rerank.rerank(query, top3_docs)

        weather_original_idx = 1
        assert weather_original_idx not in top3_indices
        assert len(reranked) == 3
        best_score = reranked[0][1]
        assert best_score > 0.5


# ---------------------------------------------------------------------------
# OpenAI 兼容 Provider 单元测试
# ---------------------------------------------------------------------------

class TestOpenAICompatibleProvider:
    """OpenAI 兼容 Provider 单元测试（构造 + 错误路径，不发真实网络请求）."""

    def test_construct(self):
        from mbforge.backends.qwen3 import OpenAICompatibleProvider
        p = OpenAICompatibleProvider(
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "sk-test", "text-embedding-v4",
        )
        assert p._base_url == "https://dashscope.aliyuncs.com/compatible-mode/v1"
        assert p._api_key == "sk-test"
        assert p._model == "text-embedding-v4"
        assert p._client is None
        assert p._dim == 0

    def test_load_requires_api_key(self):
        from mbforge.backends.qwen3 import OpenAICompatibleProvider
        p = OpenAICompatibleProvider("https://example.com", "", "model")
        with pytest.raises(ValueError, match="api_key is empty"):
            p.load()

    def test_load_requires_base_url(self):
        from mbforge.backends.qwen3 import OpenAICompatibleProvider
        p = OpenAICompatibleProvider("", "sk-test", "model")
        with pytest.raises(ValueError, match="base_url is empty"):
            p.load()

    def test_health_unloaded(self):
        from mbforge.backends.qwen3 import OpenAICompatibleProvider
        p = OpenAICompatibleProvider("https://example.com", "k", "m")
        h = p.health()
        assert h["status"] == "loading"

    def test_health_loaded(self):
        from mbforge.backends.qwen3 import OpenAICompatibleProvider
        p = OpenAICompatibleProvider("https://example.com", "k", "m")
        p._client = MagicMock()
        assert p.health()["status"] == "ready"

    def test_unload_clears_state(self):
        from mbforge.backends.qwen3 import OpenAICompatibleProvider
        p = OpenAICompatibleProvider("https://example.com", "k", "m")
        p._client = MagicMock()
        p._error = "test"
        p.unload()
        assert p._client is None
        assert p._error == ""

    def test_embed_empty_returns_empty(self):
        from mbforge.backends.qwen3 import OpenAICompatibleProvider
        p = OpenAICompatibleProvider("https://example.com", "k", "m")
        p._client = MagicMock()
        assert p.embed([]) == []

    def test_embed_calls_client_and_sorts(self):
        """embed() 调用 OpenAI client，按 index 排序后返回."""
        from mbforge.backends.qwen3 import OpenAICompatibleProvider
        p = OpenAICompatibleProvider("https://example.com", "k", "m")
        p._client = MagicMock()
        resp = MagicMock()
        resp.data = [
            MagicMock(index=1, embedding=[0.2, 0.2]),
            MagicMock(index=0, embedding=[0.1, 0.1]),
        ]
        p._client.embeddings.create = MagicMock(return_value=resp)
        result = p.embed(["a", "b"])
        p._client.embeddings.create.assert_called_once_with(
            model="m", input=["a", "b"]
        )
        assert result == [[0.1, 0.1], [0.2, 0.2]]

    def test_embed_mrl_dim_truncates(self):
        from mbforge.backends.qwen3 import OpenAICompatibleProvider
        p = OpenAICompatibleProvider("https://example.com", "k", "m")
        p._client = MagicMock()
        resp = MagicMock()
        resp.data = [MagicMock(index=0, embedding=[0.1, 0.2, 0.3, 0.4])]
        p._client.embeddings.create = MagicMock(return_value=resp)
        result = p.embed(["a"], mrl_dim=2)
        assert result == [[0.1, 0.2]]

    def test_build_provider_falls_back_to_local_when_no_apikey(self):
        """provider=openai_compatible 但 api_key 为空 → 强制走本地."""
        from mbforge.backends.qwen3 import _build_embed_provider, LocalSentenceTransformerProvider
        from unittest.mock import patch
        mock_cfg = MagicMock()
        mock_cfg.embed.provider = "openai_compatible"
        mock_cfg.embed.api_key = ""
        mock_cfg.embed.base_url = "https://x"
        mock_cfg.embed.model_name = "Qwen/Qwen3-Embedding-0.6B"
        mock_cfg.embed.device = "cpu"
        mock_cfg.embed.instruction = "instruct"
        with patch("mbforge.backends.qwen3.load_global_config", return_value=mock_cfg):
            with patch.dict("os.environ", {}, clear=True):
                p = _build_embed_provider()
        assert isinstance(p, LocalSentenceTransformerProvider)

    def test_build_provider_uses_external_when_apikey_set(self):
        """provider=openai_compatible + api_key → 外部 provider."""
        from mbforge.backends.qwen3 import _build_embed_provider, OpenAICompatibleProvider
        from unittest.mock import patch
        mock_cfg = MagicMock()
        mock_cfg.embed.provider = "openai_compatible"
        mock_cfg.embed.api_key = "sk-real"
        mock_cfg.embed.base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        mock_cfg.embed.model_name = "text-embedding-v4"
        with patch("mbforge.backends.qwen3.load_global_config", return_value=mock_cfg):
            p = _build_embed_provider()
        assert isinstance(p, OpenAICompatibleProvider)
        assert p._model == "text-embedding-v4"
        assert p._api_key == "sk-real"

    def test_build_provider_default_is_local(self):
        """provider='qwen3'（默认） → 走本地."""
        from mbforge.backends.qwen3 import _build_embed_provider, LocalSentenceTransformerProvider
        from unittest.mock import patch
        mock_cfg = MagicMock()
        mock_cfg.embed.provider = "qwen3"
        mock_cfg.embed.api_key = ""
        mock_cfg.embed.base_url = ""
        mock_cfg.embed.model_name = "Qwen/Qwen3-Embedding-0.6B"
        mock_cfg.embed.device = "cpu"
        mock_cfg.embed.instruction = "instruct"
        with patch("mbforge.backends.qwen3.load_global_config", return_value=mock_cfg):
            p = _build_embed_provider()
        assert isinstance(p, LocalSentenceTransformerProvider)
