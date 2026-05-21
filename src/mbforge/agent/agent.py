"""Project Agent 协调器.

轻量级 ReAct 循环：
1. 发送消息 + 可用工具给 LLM
2. LLM 选择直接回复或调用工具（function calling）
3. 如调用工具，执行并将结果加入上下文
4. 回到步骤 1，最多循环 5 次
5. 返回最终回复给用户

集成 OpenViking 和 TencentDB-Agent-Memory：
- 记忆注入（L1 project 层）
- 检索轨迹记录
- 对话结束后的记忆自迭代提取
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .context import LayeredContext
from .executor import ToolExecutor
from .memory_manager import MemoryManager
from .trajectory import TrajectoryTracker
from ..models.base import BaseLLM, Message
from ..utils.logger import get_logger

logger = get_logger(__name__)


class ProjectAgent:
    """项目级 AI Agent.

    每个项目拥有独立的 Agent 实例，包含：
    - 独立的 LayeredContext（分层上下文）
    - 绑定项目资源的 ToolExecutor
    - 持久的对话记忆（可选）
    - 6 类记忆管理（MemoryManager）
    - 检索轨迹跟踪（TrajectoryTracker）
    """

    DEFAULT_SYSTEM_PROMPT = (
        "你是一位专业的药物化学和分子生物学研究助手。"
        "你可以使用工具来查询项目中的知识库、分子数据库和文档。"
        "请用中文回答用户的问题。"
    )

    def __init__(
        self,
        llm: Optional[BaseLLM] = None,
        tool_executor: Optional[ToolExecutor] = None,
        system_prompt: str = "",
        max_iterations: int = 5,
        project_root: Optional[Path] = None,
    ):
        self.llm = llm
        self.tool_executor = tool_executor
        self.max_iterations = max_iterations
        self.project_root = project_root

        self.context = LayeredContext(
            system_prompt=system_prompt or self.DEFAULT_SYSTEM_PROMPT,
            max_history_rounds=20,
        )

        # 记忆与轨迹
        self.memory_manager: Optional[MemoryManager] = None
        self.trajectory_tracker: Optional[TrajectoryTracker] = None
        if project_root is not None:
            self.memory_manager = MemoryManager(project_root)
            self.trajectory_tracker = TrajectoryTracker(project_root)
            self._inject_memories()

        if tool_executor is not None:
            # 在系统提示中追加可用工具说明
            self._inject_tool_descriptions()

    def _inject_tool_descriptions(self) -> None:
        """将可用工具信息注入系统提示."""
        if self.tool_executor is None:
            return
        tools = self.tool_executor.registry.list_tools()
        if not tools:
            return
        lines = ["\n[可用工具]"]
        for t in tools:
            lines.append(f"- {t.name}: {t.description}")
        desc = "\n".join(lines)
        # 追加到系统提示
        if self.context._system.messages:
            original = self.context._system.messages[0].content
            self.context.set_system_prompt(original + desc)
        else:
            self.context.set_system_prompt(self.DEFAULT_SYSTEM_PROMPT + desc)

    def _inject_memories(self) -> None:
        """将用户画像和 Agent 经验注入项目上下文."""
        if self.memory_manager is None:
            return
        user_profile = self.memory_manager.get_user_profile_text()
        if user_profile:
            self.context.inject_memory(user_profile)
        agent_memory = self.memory_manager.get_agent_memory_text()
        if agent_memory:
            self.context.inject_agent_memory(agent_memory)

    def set_project_context(self, project_name: str, project_path: str) -> None:
        """设置当前项目上下文."""
        self.context.set_project_context(
            f"当前项目: {project_name}\n项目路径: {project_path}"
        )

    def chat(self, user_input: str) -> str:
        """同步对话（无流式）.

        执行 ReAct 循环，返回最终回复。
        """
        if self.llm is None:
            return "LLM 未配置，请在设置中配置模型。"

        self.context.add_user_message(user_input)

        final_answer = ""
        for i in range(self.max_iterations):
            logger.debug(f"Agent iteration {i + 1}/{self.max_iterations}")

            messages = self.context.build_messages()

            # 如果有工具，请求 function calling
            if self.tool_executor is not None:
                tools = self.tool_executor.registry.to_openai_schemas()
                response = self._call_llm_with_tools(messages, tools)
            else:
                response = self._call_llm(messages)

            # 解析响应
            content, tool_calls = self._parse_response(response)

            if tool_calls:
                # 执行工具
                self.context.add_assistant_message(content or "", tool_calls=tool_calls)
                for tc in tool_calls:
                    result = self._execute_tool_call(tc)
                    self.context.add_tool_result(
                        tc["name"], result, tool_call_id=tc.get("id", "")
                    )
                    # 记录轨迹
                    if self.trajectory_tracker is not None:
                        self.trajectory_tracker.record_tool(
                            tc["name"],
                            tc.get("arguments", {}),
                            result[:200],
                        )
                continue
            else:
                # 直接回复
                final_answer = content or ""
                self.context.add_assistant_message(final_answer)
                break

        # 清理临时工具结果
        self.context.clear_tool_results()
        return final_answer

    def chat_stream(self, user_input: str):
        """流式对话生成器（简化版，不执行工具循环）.

        由于流式输出难以在中间插入工具调用，
        简化策略：先检查是否需要工具，如需要则同步执行后再流式输出最终答案。
        """
        if self.llm is None:
            yield "LLM 未配置，请在设置中配置模型。"
            return

        # 先判断是否需要工具（一轮快速调用）
        self.context.add_user_message(user_input)

        if self.tool_executor is not None:
            messages = self.context.build_messages()
            tools = self.tool_executor.registry.to_openai_schemas()
            response = self._call_llm_with_tools(messages, tools)
            content, tool_calls = self._parse_response(response)

            if tool_calls:
                # 执行所有工具
                self.context.add_assistant_message(content or "", tool_calls=tool_calls)
                for tc in tool_calls:
                    result = self._execute_tool_call(tc)
                    self.context.add_tool_result(
                        tc["name"], result, tool_call_id=tc.get("id", "")
                    )
                    if self.trajectory_tracker is not None:
                        self.trajectory_tracker.record_tool(
                            tc["name"],
                            tc.get("arguments", {}),
                            result[:200],
                        )

                # 再请求最终回复并流式输出
                final_messages = self.context.build_messages()
                full_text = ""
                for chunk in self.llm.chat_stream(final_messages):
                    yield chunk.delta
                    full_text += chunk.delta
                self.context.add_assistant_message(full_text)
                self.context.clear_tool_results()
                return

        # 不需要工具，直接流式输出
        messages = self.context.build_messages()
        full_text = ""
        for chunk in self.llm.chat_stream(messages):
            yield chunk.delta
            full_text += chunk.delta
        self.context.add_assistant_message(full_text)
        self.context.clear_tool_results()

    def extract_memory(self) -> None:
        """从当前对话历史中自动提取记忆（TencentDB 记忆自迭代）."""
        if self.memory_manager is None or self.llm is None:
            return
        messages = self.context.build_messages(include_tools=False)
        self.memory_manager.extract_from_conversation(messages, self.llm)

    # ---- 内部方法 ----

    def _call_llm(self, messages: List[Message]) -> Any:
        """基础 LLM 调用."""
        return self.llm.chat(messages)

    def _call_llm_with_tools(self, messages: List[Message], tools: List[Dict]) -> Any:
        """带工具定义的 LLM 调用。委托给 BaseLLM.call_with_tools()。"""
        try:
            return self.llm.call_with_tools(messages, tools)
        except Exception as e:
            logger.exception(f"Function calling not available: {e}")
            return self.llm.chat(messages)

    def _parse_response(self, response: Any) -> tuple[str, List[Dict]]:
        """解析 LLM 响应，提取内容和工具调用.

        Returns:
            (content, tool_calls_list)
        """
        content = ""
        tool_calls = []

        # Anthropic response object (MiniMax Anthropic-compatible)
        if hasattr(response, "content") and not hasattr(response, "choices"):
            for block in response.content:
                if block.type == "text":
                    content += block.text
                elif block.type == "tool_use":
                    tool_calls.append({
                        "id": getattr(block, "id", ""),
                        "name": block.name,
                        "arguments": dict(block.input) if hasattr(block, "input") and block.input else {},
                    })
            return content, tool_calls

        # OpenAI response object
        if hasattr(response, "choices"):
            choice = response.choices[0]
            msg = choice.message
            content = getattr(msg, "content", "") or ""
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    try:
                        args = json.loads(tc.function.arguments)
                    except Exception:
                        args = {}
                    tool_calls.append({
                        "id": getattr(tc, "id", ""),
                        "name": tc.function.name,
                        "arguments": args,
                    })
            return content, tool_calls

        # 纯字符串回复
        content = str(response)
        return content, tool_calls

    def _execute_tool_call(self, tool_call: Dict) -> str:
        """执行单个工具调用."""
        name = tool_call["name"]
        args = tool_call.get("arguments", {})
        logger.info(f"Executing tool: {name}({args})")
        if self.tool_executor is None:
            return "错误：工具执行器未初始化"
        return self.tool_executor.registry.call(name, args)

    def clear(self) -> None:
        """清空对话历史."""
        self.context.clear_history()
