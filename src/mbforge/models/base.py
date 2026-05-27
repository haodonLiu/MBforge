"""AI 模型基类与通用接口."""

from __future__ import annotations

import asyncio
import functools
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, TypeVar
from collections.abc import AsyncGenerator, Callable, Iterator

T = TypeVar("T")


async def run_sync_async(func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Run a synchronous function in a thread pool executor.

    Use this to wrap sync methods into async ones without duplicating
    the asyncio.get_running_loop() + run_in_executor pattern.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        functools.partial(func, *args, **kwargs),
    )


@dataclass
class Message:
    """对话消息."""

    role: str  # system | user | assistant | tool
    content: str
    attachments: list[str] | None = None  # 附件路径，用于 VLM
    tool_call_id: str | None = None  # 工具调用 ID（用于 function calling）
    name: str | None = None  # 工具名（用于 tool 消息）
    tool_calls: list | None = None  # 工具调用列表（用于 assistant 消息）


@dataclass
class StreamChunk:
    """流式输出块."""

    delta: str
    finish_reason: str | None = None


class BaseLLM(ABC):
    """LLM 基类."""

    @abstractmethod
    def chat(self, messages: list[Message], **kwargs) -> str:
        """同步对话，返回完整回复."""
        ...

    @abstractmethod
    def chat_stream(self, messages: list[Message], **kwargs) -> Iterator[StreamChunk]:
        """同步流式对话."""
        ...

    @abstractmethod
    async def achat(self, messages: list[Message], **kwargs) -> str:
        """异步对话."""
        ...

    @abstractmethod
    async def achat_stream(
        self, messages: list[Message], **kwargs
    ) -> AsyncGenerator[StreamChunk, None]:
        """异步流式对话."""
        ...

    def call_with_tools(
        self, messages: list[Message], tools: list[dict], **kwargs
    ) -> Any:
        """带工具定义的 LLM 调用。默认 fallback 到 chat()。"""
        return self.chat(messages, **kwargs)


class BaseEmbedder(ABC):
    """Embedding 模型基类."""

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """同步编码文本，返回向量列表."""
        ...

    @abstractmethod
    async def aembed(self, texts: list[str]) -> list[list[float]]:
        """异步编码文本."""
        ...


class BaseReranker(ABC):
    """Rerank 模型基类."""

    @abstractmethod
    def rerank(self, query: str, passages: list[str]) -> list[tuple[int, float]]:
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
