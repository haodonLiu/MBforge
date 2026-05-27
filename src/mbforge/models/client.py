"""模型服务 HTTP 客户端（替代直接模型调用）."""

from __future__ import annotations

import json
from typing import AsyncIterator

import httpx

from .base import Message, StreamChunk


class LLMClient:
    """LLM HTTP 客户端."""

    def __init__(self, base_url: str = "http://127.0.0.1:18792"):
        self.base_url = base_url
        self._http = httpx.AsyncClient(timeout=60.0)

    async def chat(self, messages: list[Message], **kwargs) -> str:
        payload = {
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 4096),
        }
        resp = await self._http.post(f"{self.base_url}/api/v1/llm/chat", json=payload)
        data = resp.json()
        return data.get("content", "")

    async def chat_stream(self, messages: list[Message], **kwargs) -> AsyncIterator[StreamChunk]:
        payload = {
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 4096),
        }
        async with self._http.stream("POST", f"{self.base_url}/api/v1/llm/chat-stream", json=payload) as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    d = json.loads(line[6:])
                    yield StreamChunk(delta=d.get("delta", ""), finish_reason=d.get("finish_reason"))

    async def aclose(self) -> None:
        await self._http.aclose()


class EmbedClient:
    """Embedder HTTP 客户端."""

    def __init__(self, base_url: str = "http://127.0.0.1:18792"):
        self.base_url = base_url
        self._http = httpx.AsyncClient(timeout=30.0)

    async def embed(self, texts: list[str], **kwargs) -> list[list[float]]:
        payload = {"texts": texts, "model": kwargs.get("model", "sentence_transformers")}
        resp = await self._http.post(f"{self.base_url}/api/v1/embed", json=payload)
        return resp.json().get("embeddings", [])

    async def aclose(self) -> None:
        await self._http.aclose()


class RerankClient:
    """Reranker HTTP 客户端."""

    def __init__(self, base_url: str = "http://127.0.0.1:18792"):
        self.base_url = base_url
        self._http = httpx.AsyncClient(timeout=30.0)

    async def rerank(self, query: str, passages: list[str], top_n: int = 5, **kwargs) -> list[tuple[int, float]]:
        payload = {
            "query": query,
            "passages": passages,
            "top_n": top_n,
            "model": kwargs.get("model", "sentence_transformers"),
        }
        resp = await self._http.post(f"{self.base_url}/api/v1/rerank", json=payload)
        results = resp.json().get("results", [])
        return [(r["index"], r["score"]) for r in results]

    async def aclose(self) -> None:
        await self._http.aclose()


class VLMClient:
    """VLM HTTP 客户端."""

    def __init__(self, base_url: str = "http://127.0.0.1:18792"):
        self.base_url = base_url
        self._http = httpx.AsyncClient(timeout=60.0)

    async def describe(self, image_base64: str, prompt: str = "", **kwargs) -> str:
        payload = {"image_base64": image_base64, "prompt": prompt}
        resp = await self._http.post(f"{self.base_url}/api/v1/vlm/describe", json=payload)
        return resp.json().get("description", "")

    async def aclose(self) -> None:
        await self._http.aclose()


class UniParserClient:
    """UniParser HTTP 客户端."""

    def __init__(self, base_url: str = "http://127.0.0.1:18792"):
        self.base_url = base_url
        self._http = httpx.AsyncClient(timeout=300.0)

    async def parse_pdf(self, pdf_path: str = "", pdf_base64: str = "", **kwargs) -> dict:
        payload = {
            "pdf_path": pdf_path,
            "pdf_base64": pdf_base64,
            "sync": kwargs.get("sync", True),
            "textual": kwargs.get("textual", 2),
            "table": kwargs.get("table", 2),
            "equation": kwargs.get("equation", 2),
            "chart": kwargs.get("chart", -1),
            "figure": kwargs.get("figure", -1),
            "expression": kwargs.get("expression", -1),
            "molecule": kwargs.get("molecule", 1),
        }
        resp = await self._http.post(f"{self.base_url}/api/v1/uniparser/parse", json=payload)
        return resp.json()

    async def get_result(self, token: str, **kwargs) -> dict:
        payload = {"token": token, **kwargs}
        resp = await self._http.post(f"{self.base_url}/api/v1/uniparser/result", json=payload)
        return resp.json()

    async def get_formatted(self, token: str, **kwargs) -> dict:
        payload = {"token": token, **kwargs}
        resp = await self._http.post(f"{self.base_url}/api/v1/uniparser/formatted", json=payload)
        return resp.json()

    async def health(self) -> dict:
        resp = await self._http.get(f"{self.base_url}/api/v1/uniparser/health")
        return resp.json()

    async def aclose(self) -> None:
        await self._http.aclose()


class MolDetClient:
    """MolDet HTTP 客户端."""

    def __init__(self, base_url: str = "http://127.0.0.1:18792"):
        self.base_url = base_url
        self._http = httpx.AsyncClient(timeout=60.0)

    async def detect_page(self, image_base64: str) -> dict:
        payload = {"image_base64": image_base64}
        resp = await self._http.post(f"{self.base_url}/api/v1/moldet/detect-page", json=payload)
        return resp.json()

    async def extract_page(self, image_base64: str, page_idx: int = 0, page_w_pts: float = 595.0,
                           page_h_pts: float = 842.0, image_w: int = 0, image_h: int = 0, dpi: float = 300.0) -> dict:
        payload = {
            "image_base64": image_base64,
            "page_idx": page_idx,
            "page_w_pts": page_w_pts,
            "page_h_pts": page_h_pts,
            "image_w": image_w,
            "image_h": image_h,
            "dpi": dpi,
        }
        resp = await self._http.post(f"{self.base_url}/api/v1/moldet/extract-page", json=payload)
        return resp.json()

    async def extract_region(self, image_base64: str, page_idx: int = 0, bbox_pdf: tuple | None = None) -> dict:
        payload = {"image_base64": image_base64, "page_idx": page_idx}
        if bbox_pdf:
            payload["bbox_pdf"] = bbox_pdf
        resp = await self._http.post(f"{self.base_url}/api/v1/moldet/extract-region", json=payload)
        return resp.json()

    async def health(self) -> dict:
        resp = await self._http.get(f"{self.base_url}/api/v1/moldet/health")
        return resp.json()

    async def aclose(self) -> None:
        await self._http.aclose()


class ModelClientFactory:
    """工厂类：根据连接状态返回 HTTP 客户端或直接模型实例."""

    def __init__(self, base_url: str = "http://127.0.0.1:18792"):
        self.base_url = base_url
        self._http_available: bool | None = None
        self._llm_client = LLMClient(base_url)
        self._embed_client = EmbedClient(base_url)
        self._rerank_client = RerankClient(base_url)
        self._vlm_client = VLMClient(base_url)
        self._uniparser_client = UniParserClient(base_url)
        self._moldet_client = MolDetClient(base_url)

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

    def get_uniparser(self):
        # UniParser 是外部服务，HTTP 模式下走代理，否则直接连接
        if self._check_http():
            return self._uniparser_client
        from ..parsers.uniparser.uniparser_client import ParserClient
        from ..parsers.uniparser.uniparser_config import load_config
        return ParserClient(load_config())

    def get_moldet(self):
        if self._check_http():
            return self._moldet_client
        from ..parsers.molecule.mol_image_pipeline import MolImagePipeline
        from ..utils.config import load_global_config
        return MolImagePipeline(device=load_global_config().embed.device)
