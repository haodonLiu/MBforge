"""分层对话上下文管理.

解决简单 message 列表的问题：
- 不同层级的消息有不同的生命周期和优先级
- 支持智能裁剪，确保总 token 不超限
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from ..models.base import Message
from ..utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ContextLayer:
    """上下文层."""

    name: str
    messages: List[Message] = field(default_factory=list)
    priority: int = 0  # 优先级：数字越小越重要，越不容易被裁剪
    max_tokens: int = 0  # 0 表示不限制
    ephemeral: bool = False  # True 表示该层消息不会被持久化

    def add(self, role: str, content: str, **kwargs) -> None:
        self.messages.append(Message(role=role, content=content, **kwargs))

    def clear(self) -> None:
        self.messages.clear()


class LayeredContext:
    """分层上下文管理器.

    四层架构：
    - L0 system:   系统提示（永久保留）
    - L1 project:  项目上下文（当前打开的文件、项目信息等）
    - L2 tools:    工具调用结果（临时，ephemeral）
    - L3 history:  对话历史（可裁剪，只保留最近 N 轮）
    """

    def __init__(
        self,
        system_prompt: str = "",
        max_history_rounds: int = 20,
        max_total_tokens: int = 32000,
    ):
        self.max_history_rounds = max_history_rounds
        self.max_total_tokens = max_total_tokens

        self._layers: List[ContextLayer] = [
            ContextLayer("system", priority=0),    # L0
            ContextLayer("project", priority=1),   # L1
            ContextLayer("tools", priority=2, ephemeral=True),  # L2
            ContextLayer("history", priority=3),   # L3
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
        """注入用户记忆到项目上下文（OpenViking / TencentDB）."""
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

    def add_tool_result(self, tool_name: str, result: str, tool_call_id: str = "") -> None:
        """添加工具调用结果（临时层，不持久化）."""
        self._tools.add(
            "tool",
            f'[工具调用结果: {tool_name}]\n{result[:4000]}',
            name=tool_name,
            tool_call_id=tool_call_id,
        )

    def clear_tool_results(self) -> None:
        self._tools.clear()

    # ---- 对话历史 ----

    def add_user_message(self, content: str) -> None:
        self._history.add("user", content)

    def add_assistant_message(self, content: str) -> None:
        self._history.add("assistant", content)

    def trim_history(self) -> None:
        """裁剪对话历史，只保留最近 N 轮."""
        msgs = self._history.messages
        if len(msgs) <= self.max_history_rounds * 2:
            return
        # 保留最近的 N 轮（user + assistant 算一轮）
        keep = self.max_history_rounds * 2
        self._history.messages = msgs[-keep:]
        logger.debug(f"History trimmed to {keep} messages")

    def clear_history(self) -> None:
        self._history.clear()
        self._tools.clear()

    # ---- 组装消息 ----

    def build_messages(
        self,
        include_tools: bool = True,
        include_history: bool = True,
    ) -> List[Message]:
        """按优先级组装消息列表，供 LLM 调用."""
        result: List[Message] = []

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

        return result

    # ---- 序列化（用于持久化）----

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典（不含 ephemeral 层）."""
        return {
            "system": [m.__dict__ for m in self._system.messages],
            "project": [m.__dict__ for m in self._project.messages],
            "history": [m.__dict__ for m in self._history.messages],
            "max_history_rounds": self.max_history_rounds,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> LayeredContext:
        ctx = cls(
            max_history_rounds=data.get("max_history_rounds", 20),
        )
        ctx._system.messages = [Message(**m) for m in data.get("system", [])]
        ctx._project.messages = [Message(**m) for m in data.get("project", [])]
        ctx._history.messages = [Message(**m) for m in data.get("history", [])]
        return ctx
