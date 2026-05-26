"""模型服务 HTTP 客户端（替代直接模型调用）."""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

import httpx

from .base import Message, StreamChunk


class LLMClient:
    """LLM HTTP 客户端."""

    def __init__(self, base_url: str = "http://127.0.0.1:18792"):
        self.base_url = base_url
        self._client = httpx.AsyncClient(timeout=60.0)

    async def chat(self, messages: list[Message], **kwargs) -> str:
        payload = {
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 4096),
        }
        resp = await self._client.post(f"{self.base_url}/api/v1/llm/chat", json=payload)
        data = resp.json()
        return data.get("content", "")

    async def chat_stream(self, messages: list[Message], **kwargs) -> AsyncIterator[StreamChunk]:
        payload = {
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 4096),
        }
        async with self._client.stream("POST", f"{self.base_url}/api/v1/llm/chat-stream", json=payload) as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    d = json.loads(line[6:])
                    yield StreamChunk(delta=d.get("delta", ""), finish_reason=d.get("finish_reason"))

    async def aclose(self) -> None:
        await self._client.aclose()


class EmbedClient:
    """Embedder HTTP 客户端."""

    def __init__(self, base_url: str = "http://127.0.0.1:18792"):
        self.base_url = base_url
        self._client = httpx.AsyncClient(timeout=30.0)

    async def embed(self, texts: list[str], **kwargs) -> list[list[float]]:
        payload = {"texts": texts, "model": kwargs.get("model", "sentence_transformers")}
        resp = await self._client.post(f"{self.base_url}/api/v1/embed", json=payload)
        return resp.json().get("embeddings", [])

    async def aclose(self) -> None:
        await self._client.aclose()


class RerankClient:
    """Reranker HTTP 客户端."""

    def __init__(self, base_url: str = "http://127.0.0.1:18792"):
        self.base_url = base_url
        self._client = httpx.AsyncClient(timeout=30.0)

    async def rerank(self, query: str, passages: list[str], top_n: int = 5, **kwargs) -> list[tuple[int, float]]:
        payload = {
            "query": query,
            "passages": passages,
            "top_n": top_n,
            "model": kwargs.get("model", "sentence_transformers"),
        }
        resp = await self._client.post(f"{self.base_url}/api/v1/rerank", json=payload)
        results = resp.json().get("results", [])
        return [(r["index"], r["score"]) for r in results]

    async def aclose(self) -> None:
        await self._client.aclose()


class VLMClient:
    """VLM HTTP 客户端."""

    def __init__(self, base_url: str = "http://127.0.0.1:18792"):
        self.base_url = base_url
        self._client = httpx.AsyncClient(timeout=60.0)

    async def describe(self, image_base64: str, prompt: str = "", **kwargs) -> str:
        payload = {"image_base64": image_base64, "prompt": prompt}
        resp = await self._client.post(f"{self.base_url}/api/v1/vlm/describe", json=payload)
        return resp.json().get("description", "")

    async def aclose(self) -> None:
        await self._client.aclose()


class ModelClientFactory:
    """工厂类：根据连接状态返回 HTTP 客户端或直接模型实例."""

    def __init__(self, base_url: str = "http://127.0.0.1:18792"):
        self.base_url = base_url
        self._http_available: bool | None = None
        self._llm_client = LLMClient(base_url)
        self._embed_client = EmbedClient(base_url)
        self._rerank_client = RerankClient(base_url)
        self._vlm_client = VLMClient(base_url)

    def _check_http(self) -> bool:
        if self._http_available is not None:
            return self._http_available
        try:
            resp = httpx.get(f"{self.base_url}/api/v1/health", timeout=2.0)
            self._http_available = resp.status_code == 200
        except Exception:
            self._http_available = False
        return self._http_available

    def get_llm(self):
        if self._check_http():
            return self._llm_client
        # 降级到直接实例
        from .llm import create_llm_from_config
        from ..utils.config import load_global_config
        return create_llm_from_config(load_global_config().llm)

    def get_embedder(self):
        if self._check_http():
            return self._embed_client
        from .embedding import create_embedder_from_config
        from ..utils.config import load_global_config
        return create_embedder_from_config(load_global_config().embed)

    def get_reranker(self):
        if self._check_http():
            return self._rerank_client
        from .rerank import create_reranker_from_config
        from ..utils.config import load_global_config
        return create_reranker_from_config(load_global_config().rerank)

    def get_vlm(self):
        if self._check_http():
            return self._vlm_client
        from .vlm import create_vlm_from_config
        from ..utils.config import load_global_config
        return create_vlm_from_config(load_global_config().vlm)
