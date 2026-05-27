"""分层对话上下文管理.

解决简单 message 列表的问题：
- 不同层级的消息有不同的生命周期和优先级
- 支持 token 计数裁剪，确保总 token 不超限
- 支持持久化到本地文件
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..models.base import Message
from ..utils.logger import get_logger

logger = get_logger(__name__)


def estimate_tokens(text: str) -> int:
    """估算 token 数量（简化版：中文 ~1.5 token/字，英文 ~0.25 token/字符）."""
    chinese_chars = sum(1 for c in text if '一' <= c <= '鿿')
    other_chars = len(text) - chinese_chars
    return int(chinese_chars * 1.5 + other_chars * 0.25)


@dataclass
class ContextLayer:
    """上下文层."""

    name: str
    messages: list[Message] = field(default_factory=list)
    priority: int = 0  # 优先级：数字越小越重要，越不容易被裁剪
    max_tokens: int = 0  # 0 表示不限制
    ephemeral: bool = False  # True 表示该层消息不会被持久化

    def add(self, role: str, content: str, **kwargs) -> None:
        self.messages.append(Message(role=role, content=content, **kwargs))

    def clear(self) -> None:
        self.messages.clear()

    def token_count(self) -> int:
        """计算本层所有消息的 token 总数."""
        return sum(estimate_tokens(m.content) for m in self.messages)


class LayeredContext:
    """分层上下文管理器.

    四层架构：
    - L0 system:   系统提示（永久保留）
    - L1 project:  项目上下文（当前打开的文件、项目信息等）
    - L2 tools:    工具调用结果（临时，ephemeral）
    - L3 history:  对话历史（可裁剪，按 token 裁剪）
    """

    def __init__(
        self,
        system_prompt: str = "",
        max_history_rounds: int = 20,
        max_total_tokens: int = 32000,
    ):
        self.max_history_rounds = max_history_rounds
        self.max_total_tokens = max_total_tokens

        self._layers: list[ContextLayer] = [
            ContextLayer("system", priority=0),  # L0
            ContextLayer("project", priority=1),  # L1
            ContextLayer("tools", priority=2, ephemeral=True),  # L2
            ContextLayer("history", priority=3),  # L3
        ]

        if system_prompt:
            self.set_system_prompt(system_prompt)

    # ---- 快捷访问 ----

    @property
    def _system(self) -> ContextLayer:
        return self._layers[0]

    @property
    def _project(self) -> ContextLayer:
        return self._layers[1]

    @property
    def _tools(self) -> ContextLayer:
        return self._layers[2]

    @property
    def _history(self) -> ContextLayer:
        return self._layers[3]

    # ---- Token 计算 ----

    def total_token_count(self) -> int:
        """计算所有非 ephemeral 层的 token 总数."""
        return sum(
            layer.token_count()
            for layer in self._layers
            if not layer.ephemeral
        )

    # ---- 系统提示 ----

    def set_system_prompt(self, prompt: str) -> None:
        self._system.messages = [Message(role="system", content=prompt)]

    # ---- 项目上下文 ----

    def set_project_context(self, context: str) -> None:
        """设置项目级上下文（会覆盖旧的）."""
        self._project.messages = [
            Message(role="system", content=f"[项目上下文]\n{context}")
        ]

    def update_project_context(self, context: str) -> None:
        """追加项目上下文."""
        self._project.add("system", f"[项目上下文更新]\n{context}")

    def clear_project_context(self) -> None:
        self._project.clear()

    def inject_memory(self, memory_text: str) -> None:
        """注入用户记忆到项目上下文."""
        if not memory_text:
            return
        self._project.add("system", f"[用户记忆]\n{memory_text}")

    def inject_agent_memory(self, memory_text: str) -> None:
        """注入 Agent 学习记忆到项目上下文."""
        if not memory_text:
            return
        self._project.add("system", f"[Agent 经验]\n{memory_text}")

    def inject_retrieval_trajectory(self, trajectory_text: str) -> None:
        """注入检索轨迹到项目上下文（临时，不持久化）."""
        if not trajectory_text:
            return
        self._tools.add("system", f"[检索轨迹]\n{trajectory_text}")

    # ---- 工具结果 ----

    def add_tool_result(
        self, tool_name: str, result: str, tool_call_id: str = ""
    ) -> None:
        """添加工具调用结果到历史层."""
        self._history.add(
            "tool",
            f"[工具调用结果: {tool_name}]\n{result[:4000]}",
            name=tool_name,
            tool_call_id=tool_call_id,
        )

    def clear_tool_results(self) -> None:
        self._tools.clear()

    # ---- 对话历史 ----

    def add_user_message(self, content: str) -> None:
        self._history.add("user", content)

    def add_assistant_message(
        self, content: str, tool_calls: list[dict] | None = None
    ) -> None:
        self._history.add("assistant", content, tool_calls=tool_calls or None)

    def trim_history(self) -> None:
        """基于 token 计数裁剪对话历史，确保不超过 max_total_tokens."""
        # 先按轮次裁剪
        msgs = self._history.messages
        if len(msgs) > self.max_history_rounds * 2:
            keep = self.max_history_rounds * 2
            self._history.messages = msgs[-keep:]
            logger.debug(f"History trimmed to {keep} messages (round limit)")

        # 再按 token 裁剪
        while self.total_token_count() > self.max_total_tokens and len(self._history.messages) > 2:
            # 移除最早的一轮（user + assistant）
            removed = self._history.messages.pop(0)
            if self._history.messages and self._history.messages[0].role == "assistant":
                self._history.messages.pop(0)
            logger.debug(f"Trimmed message to fit token limit (removed: {removed.content[:50]}...)")

    def clear_history(self) -> None:
        self._history.clear()
        self._tools.clear()

    # ---- 组装消息 ----

    VALID_ROLES = {"system", "user", "assistant", "tool"}

    def build_messages(
        self,
        include_tools: bool = True,
        include_history: bool = True,
    ) -> list[Message]:
        """按优先级组装消息列表，供 LLM 调用."""
        result: list[Message] = []

        # L0: system（必须）
        result.extend(self._system.messages)

        # L1: project
        result.extend(self._project.messages)

        # L2: tools（临时结果）
        if include_tools:
            result.extend(self._tools.messages)

        # L3: history
        if include_history:
            self.trim_history()
            result.extend(self._history.messages)

        # Validate roles
        for msg in result:
            if msg.role not in self.VALID_ROLES:
                raise ValueError(f"Invalid message role: {msg.role}")

        return result

    # ---- 持久化 ----

    def save_to_file(self, path: Path) -> None:
        """保存上下文到本地文件（不含 ephemeral 层）."""
        path.parent.mkdir(parents=True, exist_ok=True)
        data = self.to_dict()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.debug(f"Context saved to {path}")

    @classmethod
    def load_from_file(cls, path: Path) -> LayeredContext | None:
        """从本地文件加载上下文."""
        if not path.exists():
            return None
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return cls.from_dict(data)
        except Exception as e:
            logger.warning(f"Failed to load context from {path}: {e}")
            return None

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典（不含 ephemeral 层）."""
        return {
            "system": [m.__dict__ for m in self._system.messages],
            "project": [m.__dict__ for m in self._project.messages],
            "history": [m.__dict__ for m in self._history.messages],
            "max_history_rounds": self.max_history_rounds,
            "max_total_tokens": self.max_total_tokens,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LayeredContext:
        ctx = cls(
            max_history_rounds=data.get("max_history_rounds", 20),
            max_total_tokens=data.get("max_total_tokens", 32000),
        )
        ctx._system.messages = [Message(**m) for m in data.get("system", [])]
        ctx._project.messages = [Message(**m) for m in data.get("project", [])]
        ctx._history.messages = [Message(**m) for m in data.get("history", [])]
        return ctx
