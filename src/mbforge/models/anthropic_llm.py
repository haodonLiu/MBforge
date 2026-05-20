"""Anthropic 兼容 API 的 LLM 实现（用于 MiniMax 等）."""

from __future__ import annotations

from typing import Any, Dict, Iterator, List, Tuple

from .base import BaseLLM, Message, StreamChunk


class AnthropicLLM(BaseLLM):
    """Anthropic SDK 兼容的 LLM 实现.

    主要用于 MiniMax Anthropic 兼容接口：
        base_url = "https://api.minimaxi.com/anthropic"
    """

    def __init__(
        self,
        base_url: str = "https://api.minimaxi.com/anthropic",
        api_key: str = "",
        model_name: str = "MiniMax-M2.7",
        max_tokens: int = 4096,
        temperature: float = 1.0,
        top_p: float = 0.9,
    ):
        import anthropic

        if not api_key or api_key.strip() == "":
            raise ValueError("AnthropicLLM: api_key is empty. Please check your configuration.")

        self.client = anthropic.Anthropic(
            api_key=api_key,
            base_url=base_url,
            timeout=120,
        )
        self.model_name = model_name
        # MiniMax 模型 max_tokens 上限为 196608
        self.max_tokens = min(max_tokens, 196608)
        self.temperature = temperature
        self.top_p = top_p

    # ---- 消息格式转换 ----

    def _convert_messages(self, messages: List[Message]) -> Tuple[str, List[dict]]:
        """将 MBForge Message 转为 Anthropic 格式.

        Returns:
            (system_text, anthropic_messages)
        """
        system_parts: List[str] = []
        anthropic_msgs: List[dict] = []

        for m in messages:
            if m.role == "system":
                system_parts.append(m.content)
                continue

            if m.role == "tool":
                # Anthropic tool_result 块
                # Note: 不传 tool_use_id，因为部分 API（如 MiniMax Anthropic 兼容接口）
                # 不支持外部传入的工具调用 ID，会返回 "tool id not found" 错误
                content_blocks: List[dict] = [
                    {
                        "type": "tool_result",
                        "content": m.content,
                    }
                ]
                anthropic_msgs.append({"role": "user", "content": content_blocks})
                continue

            # user / assistant
            content_blocks = [{"type": "text", "text": m.content}]
            anthropic_msgs.append({"role": m.role, "content": content_blocks})

        system_text = "\n".join(system_parts).strip()
        return system_text, anthropic_msgs

    def _convert_tools(self, openai_tools: List[dict]) -> List[dict]:
        """将 OpenAI 格式 tools 转为 Anthropic 格式."""
        anthropic_tools = []
        for t in openai_tools:
            func = t.get("function", {})
            anthropic_tools.append({
                "name": func.get("name", ""),
                "description": func.get("description", ""),
                "input_schema": func.get("parameters", {"type": "object", "properties": {}}),
            })
        return anthropic_tools

    def _build_params(self, messages: List[Message], **kwargs) -> Dict[str, Any]:
        """构建 Anthropic API 参数."""
        system, msgs = self._convert_messages(messages)
        max_tokens = min(kwargs.get("max_tokens", self.max_tokens), 196608)
        params: Dict[str, Any] = {
            "model": self.model_name,
            "max_tokens": max_tokens,
            "messages": msgs,
        }
        if system:
            params["system"] = system

        temperature = kwargs.get("temperature", self.temperature)
        if temperature is not None:
            params["temperature"] = temperature
        top_p = kwargs.get("top_p", self.top_p)
        if top_p is not None:
            params["top_p"] = top_p

        return params

    # ---- 基础对话 ----

    def chat(self, messages: List[Message], **kwargs) -> str:
        params = self._build_params(messages, **kwargs)
        response = self.client.messages.create(**params)
        return self._extract_text(response)

    def chat_stream(self, messages: List[Message], **kwargs) -> Iterator[StreamChunk]:
        params = self._build_params(messages, **kwargs)
        params["stream"] = True
        stream = self.client.messages.create(**params)
        for chunk in stream:
            if chunk.type == "content_block_delta":
                delta = chunk.delta
                if delta.type == "text_delta":
                    yield StreamChunk(delta=delta.text)
                elif delta.type == "thinking_delta":
                    # thinking 内容暂不输出给用户
                    pass
            elif chunk.type == "message_delta":
                stop_reason = chunk.delta.stop_reason if hasattr(chunk.delta, "stop_reason") else None
                yield StreamChunk(delta="", finish_reason=stop_reason)

    async def achat(self, messages: List[Message], **kwargs) -> str:
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.chat, messages, **kwargs)

    async def achat_stream(self, messages: List[Message], **kwargs):
        import asyncio
        loop = asyncio.get_event_loop()
        iterator = await loop.run_in_executor(None, self.chat_stream, messages, **kwargs)
        for chunk in iterator:
            yield chunk
            await asyncio.sleep(0)

    # ---- 工具调用 ----

    def call_with_tools(
        self,
        messages: List[Message],
        tools: List[dict],
        tool_choice: str = "auto",
        **kwargs,
    ) -> Any:
        """调用 Anthropic API 并启用工具.

        返回 Anthropic Messages 响应对象，供 agent._parse_response 解析。
        """
        params = self._build_params(messages, **kwargs)
        params["tools"] = self._convert_tools(tools)
        if tool_choice and tool_choice != "auto":
            params["tool_choice"] = {"type": "tool", "name": tool_choice}
        else:
            params["tool_choice"] = {"type": "auto"}
        return self.client.messages.create(**params)

    def call_with_tools_stream(
        self,
        messages: List[Message],
        tools: List[dict],
        tool_choice: str = "auto",
        **kwargs,
    ) -> Iterator[Any]:
        """流式调用 Anthropic API 并启用工具."""
        params = self._build_params(messages, **kwargs)
        params["tools"] = self._convert_tools(tools)
        params["stream"] = True
        if tool_choice and tool_choice != "auto":
            params["tool_choice"] = {"type": "tool", "name": tool_choice}
        else:
            params["tool_choice"] = {"type": "auto"}
        return self.client.messages.create(**params)

    # ---- 辅助方法 ----

    @staticmethod
    def _extract_text(response) -> str:
        """从 Anthropic 响应中提取文本."""
        parts = []
        for block in response.content:
            if block.type == "text":
                parts.append(block.text)
        return "\n".join(parts)
