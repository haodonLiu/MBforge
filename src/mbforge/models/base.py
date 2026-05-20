"""AI 模型基类与通用接口."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncGenerator, Iterator, List, Optional


@dataclass
class Message:
    """对话消息."""

    role: str  # system | user | assistant | tool
    content: str
    attachments: Optional[List[str]] = None  # 附件路径，用于 VLM
    tool_call_id: Optional[str] = None  # 工具调用 ID（用于 function calling）
    name: Optional[str] = None  # 工具名（用于 tool 消息）


@dataclass
class StreamChunk:
    """流式输出块."""

    delta: str
    finish_reason: Optional[str] = None


class BaseLLM(ABC):
    """LLM 基类."""

    @abstractmethod
    def chat(self, messages: List[Message], **kwargs) -> str:
        """同步对话，返回完整回复."""
        ...

    @abstractmethod
    def chat_stream(self, messages: List[Message], **kwargs) -> Iterator[StreamChunk]:
        """同步流式对话."""
        ...

    @abstractmethod
    async def achat(self, messages: List[Message], **kwargs) -> str:
        """异步对话."""
        ...

    @abstractmethod
    async def achat_stream(self, messages: List[Message], **kwargs) -> AsyncGenerator[StreamChunk, None]:
        """异步流式对话."""
        ...


class BaseEmbedder(ABC):
    """Embedding 模型基类."""

    @abstractmethod
    def embed(self, texts: List[str]) -> List[List[float]]:
        """同步编码文本，返回向量列表."""
        ...

    @abstractmethod
    async def aembed(self, texts: List[str]) -> List[List[float]]:
        """异步编码文本."""
        ...


class BaseReranker(ABC):
    """Rerank 模型基类."""

    @abstractmethod
    def rerank(self, query: str, passages: List[str]) -> List[tuple[int, float]]:
        """返回 (原始索引, 分数) 列表，按分数降序排列."""
        ...


class BaseVLM(ABC):
    """VLM 模型基类."""

    @abstractmethod
    def describe_image(self, image_path: str, prompt: str = "") -> str:
        """描述图片内容."""
        ...

    @abstractmethod
    def describe_pdf_page(self, image_path: str, context: str = "") -> str:
        """描述 PDF 页面（图表/分子结构等）."""
        ...
