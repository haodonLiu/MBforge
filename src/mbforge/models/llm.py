"""LLM 接口实现."""

from __future__ import annotations

import os
from typing import AsyncGenerator, Iterator, List, Optional

import openai

from .base import BaseLLM, Message, StreamChunk


class OpenAILLM(BaseLLM):
    """OpenAI 兼容 API 的 LLM 实现."""

    def __init__(
        self,
        base_url: str = "http://localhost:8000/v1",
        api_key: str = "",
        model_name: str = "default",
        max_tokens: int = 4096,
        temperature: float = 0.7,
        top_p: float = 0.9,
    ):
        self.client = openai.OpenAI(
            base_url=base_url,
            api_key=api_key or "empty",
            timeout=120,
        )
        self.model_name = model_name
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.top_p = top_p

    def _convert_messages(self, messages: List[Message]) -> List[dict]:
        return [
            {"role": m.role, "content": m.content}
            for m in messages
        ]

    def chat(self, messages: List[Message], **kwargs) -> str:
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=self._convert_messages(messages),
            max_tokens=kwargs.get("max_tokens", self.max_tokens),
            temperature=kwargs.get("temperature", self.temperature),
            top_p=kwargs.get("top_p", self.top_p),
            stream=False,
        )
        return response.choices[0].message.content or ""

    def chat_stream(self, messages: List[Message], **kwargs) -> Iterator[StreamChunk]:
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=self._convert_messages(messages),
            max_tokens=kwargs.get("max_tokens", self.max_tokens),
            temperature=kwargs.get("temperature", self.temperature),
            top_p=kwargs.get("top_p", self.top_p),
            stream=True,
        )
        for chunk in response:
            delta = chunk.choices[0].delta.content or ""
            finish = chunk.choices[0].finish_reason
            yield StreamChunk(delta=delta, finish_reason=finish)

    async def achat(self, messages: List[Message], **kwargs) -> str:
        # 使用同步客户端的线程池执行
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.chat, messages, **kwargs)

    async def achat_stream(self, messages: List[Message], **kwargs) -> AsyncGenerator[StreamChunk, None]:
        import asyncio
        loop = asyncio.get_event_loop()
        iterator = await loop.run_in_executor(None, self.chat_stream, messages, **kwargs)
        for chunk in iterator:
            yield chunk
            await asyncio.sleep(0)


def create_llm_from_config(config) -> BaseLLM:
    """从配置创建 LLM 实例."""
    from ..utils.config import ModelConfig
    cfg: ModelConfig = config
    return OpenAILLM(
        base_url=cfg.base_url,
        api_key=cfg.api_key,
        model_name=cfg.model_name,
        max_tokens=cfg.max_tokens,
        temperature=cfg.temperature,
        top_p=cfg.top_p,
    )
