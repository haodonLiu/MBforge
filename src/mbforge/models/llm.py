"""LLM 接口实现."""

from __future__ import annotations

from typing import Any
from collections.abc import AsyncGenerator, Iterator

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
        import openai

        self.client = openai.OpenAI(
            base_url=base_url,
            api_key=api_key or "empty",
            timeout=120,
        )
        self.model_name = model_name
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.top_p = top_p

    def _convert_messages(self, messages: list[Message]) -> list[dict]:
        return [{"role": m.role, "content": m.content} for m in messages]

    def chat(self, messages: list[Message], **kwargs) -> str:
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=self._convert_messages(messages),
            max_tokens=kwargs.get("max_tokens", self.max_tokens),
            temperature=kwargs.get("temperature", self.temperature),
            top_p=kwargs.get("top_p", self.top_p),
            stream=False,
        )
        return response.choices[0].message.content or ""

    def chat_stream(self, messages: list[Message], **kwargs) -> Iterator[StreamChunk]:
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=self._convert_messages(messages),
            max_tokens=kwargs.get("max_tokens", self.max_tokens),
            temperature=kwargs.get("temperature", self.temperature),
            top_p=kwargs.get("top_p", self.top_p),
            stream=True,
        )
        for chunk in response:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta.content or ""
            finish = chunk.choices[0].finish_reason
            yield StreamChunk(delta=delta, finish_reason=finish)

    async def achat(self, messages: list[Message], **kwargs) -> str:
        # 使用同步客户端的线程池执行
        import asyncio

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.chat, messages, **kwargs)

    async def achat_stream(
        self, messages: list[Message], **kwargs
    ) -> AsyncGenerator[StreamChunk, None]:
        import asyncio

        loop = asyncio.get_running_loop()
        iterator = await loop.run_in_executor(
            None, self.chat_stream, messages, **kwargs
        )
        for chunk in iterator:
            yield chunk
            await asyncio.sleep(0)

    def call_with_tools(
        self, messages: list[Message], tools: list[dict], **kwargs
    ) -> Any:
        return self.client.chat.completions.create(
            model=self.model_name,
            messages=self._convert_messages(messages),
            tools=tools,
            max_tokens=kwargs.get("max_tokens", self.max_tokens),
            temperature=kwargs.get("temperature", self.temperature),
        )


def create_llm_from_config(config) -> BaseLLM:
    """从配置创建 LLM 实例."""
    from ..utils.config import ModelConfig
    from ..utils.constants import PROVIDER_ANTHROPIC

    cfg: ModelConfig = config

    provider = (cfg.provider or "").strip().lower()

    if provider == PROVIDER_ANTHROPIC:
        from .anthropic_llm import AnthropicLLM

        return AnthropicLLM(
            base_url=cfg.base_url,
            api_key=cfg.api_key,
            model_name=cfg.model_name,
            max_tokens=cfg.max_tokens,
            temperature=cfg.temperature,
            top_p=cfg.top_p,
        )

    return OpenAILLM(
        base_url=cfg.base_url,
        api_key=cfg.api_key,
        model_name=cfg.model_name,
        max_tokens=cfg.max_tokens,
        temperature=cfg.temperature,
        top_p=cfg.top_p,
    )
