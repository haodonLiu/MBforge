"""Project Agent 协调器.

轻量级 ReAct 循环：
1. 发送消息 + 可用工具给 LLM
2. LLM 选择直接回复或调用工具（function calling）
3. 如调用工具，执行并将结果加入上下文
4. 回到步骤 1，最多循环 5 次
5. 返回最终回复给用户

注意：记忆管理和轨迹记录已迁移到 Rust 端（core/memory.rs, core/trajectory.rs）。
Python 端仅保留 Agent 核心逻辑和工具执行。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .context import LayeredContext
from .executor import ToolExecutor
from .optimizations import SPSConfig, SpeculativeScheduler
from ..models.base import BaseLLM, Message
from ..utils.logger import get_logger

logger = get_logger(__name__)


class ProjectAgent:
    """项目级 AI Agent."""

    DEFAULT_SYSTEM_PROMPT = """你是 MBForge 分子科学 AI 助手，服务于药物化学与分子生物学研究。

## 身份
你是一位专业的分子科学研究助手，擅长文献解读、分子数据分析、结构-活性关系（SAR）分析和药物设计建议。

## 能力范围
1. **文献检索与解读**：搜索知识库中的文献，阅读摘要、概览和全文，回答关于研究内容的问题
2. **分子数据分析**：查询分子数据库，分析分子性质、活性数据、SMILES 结构
3. **SAR 分析**：基于分子结构和活性数据，分析构效关系
4. **药物设计建议**：基于文献和分子数据，提供分子优化、先导化合物优化等建议
5. **项目管理**：查看项目文档列表、统计信息、索引状态

## 工作流程
- 收到问题后，先判断需要哪些信息，选择合适的工具获取数据
- 优先使用工具获取项目中的实际数据，而非仅依赖预训练知识
- 引用具体文档和分子数据时，注明来源
- 回答要准确、专业，使用中文学术用语

## 回答规范
- 涉及分子结构时使用 SMILES 表示
- 涉及活性数据时注明单位和数值
- 涉及文献时注明文档名称
- 不确定的内容明确标注
- 回答使用 Markdown 格式，表格用于展示对比数据

## 图片输出
当你需要展示分子结构时，将 SMILES 字符串用行内代码（反引号）包裹，前端会自动将其渲染为分子结构图。

示例：
- 阿司匹林：`CC(=O)Oc1ccccc1C(=O)O`
- 布洛芬：`CC(C)Cc1ccc(C(C)C(=O)O)cc1`

输出格式：`SMILES代码`（一对反引号包裹）

注意：
- 只输出合法的 SMILES 字符串，不要加引号或额外说明
- 如果 SMILES 无效或太长，用文本描述代替
- 对于蛋白质、核酸等大分子，用文本描述而非 SMILES"""

    def __init__(
        self,
        llm: BaseLLM | None = None,
        tool_executor: ToolExecutor | None = None,
        system_prompt: str = "",
        max_iterations: int = 5,
        project_root: Path | None = None,
    ):
        self.llm = llm
        self.tool_executor = tool_executor
        self.max_iterations = max_iterations
        self.project_root = project_root

        self.context = LayeredContext(
            system_prompt=system_prompt or self.DEFAULT_SYSTEM_PROMPT,
            max_history_rounds=20,
        )

        # SPS 优化（保留，不依赖 trajectory）
        self.sps_scheduler: SpeculativeScheduler | None = None
        if project_root is not None:
            self.sps_scheduler = SpeculativeScheduler(config=SPSConfig(enabled=True))

        if tool_executor is not None:
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
        if self.context._system.messages:
            original = self.context._system.messages[0].content
            self.context.set_system_prompt(original + desc)
        else:
            self.context.set_system_prompt(self.DEFAULT_SYSTEM_PROMPT + desc)

    def set_project_context(self, project_name: str, project_path: str) -> None:
        """设置当前项目上下文."""
        self.context.set_project_context(
            f"当前项目: {project_name}\n项目路径: {project_path}"
        )

    def chat(self, user_input: str) -> str:
        """同步对话（无流式）."""
        if self.llm is None:
            return "LLM 未配置，请在设置中配置模型。"

        self.context.add_user_message(user_input)

        final_answer = ""
        for i in range(self.max_iterations):
            logger.debug(f"Agent iteration {i + 1}/{self.max_iterations}")

            messages = self.context.build_messages()

            if self.tool_executor is not None:
                tools = self.tool_executor.registry.to_openai_schemas()
                response = self._call_llm_with_tools(messages, tools)
            else:
                response = self._call_llm(messages)

            content, tool_calls = self._parse_response(response)

            if tool_calls:
                self.context.add_assistant_message(content or "", tool_calls=tool_calls)
                for tc in tool_calls:
                    result = self._execute_tool_call(tc)
                    self.context.add_tool_result(
                        tc["name"], result, tool_call_id=tc.get("id", "")
                    )
                    # SPS: 预测并预执行下一步工具
                    if self.sps_scheduler is not None and self.sps_scheduler.config.enabled:
                        spec_calls = self.sps_scheduler.record_and_predict(
                            tc["name"],
                            tc.get("arguments", {}),
                            result[:500],
                        )
                        for spec in spec_calls:
                            if spec["confidence"] >= 0.8:
                                try:
                                    pre_result = self.tool_executor.registry.call(
                                        spec["name"], spec["args"]
                                    )
                                    self.context.add_tool_result(
                                        spec["name"],
                                        f"[预计算] {pre_result}",
                                        tool_call_id=f"spec_{spec['name']}",
                                    )
                                except Exception as e:
                                    logger.debug("SPS pre-execution skipped: %s", e)
                continue
            else:
                final_answer = content or ""
                self.context.add_assistant_message(final_answer)
                break

        self.context.clear_tool_results()
        return final_answer

    def chat_stream(self, user_input: str):
        """流式对话生成器."""
        if self.llm is None:
            yield "LLM 未配置，请在设置中配置模型。"
            return

        self.context.add_user_message(user_input)

        if self.tool_executor is not None:
            messages = self.context.build_messages()
            tools = self.tool_executor.registry.to_openai_schemas()
            response = self._call_llm_with_tools(messages, tools)
            content, tool_calls = self._parse_response(response)

            if tool_calls:
                self.context.add_assistant_message(content or "", tool_calls=tool_calls)
                for tc in tool_calls:
                    result = self._execute_tool_call(tc)
                    self.context.add_tool_result(
                        tc["name"], result, tool_call_id=tc.get("id", "")
                    )

                final_messages = self.context.build_messages()
                full_text = ""
                for chunk in self.llm.chat_stream(final_messages):
                    yield chunk.delta
                    full_text += chunk.delta
                self.context.add_assistant_message(full_text)
                self.context.clear_tool_results()
                return

        messages = self.context.build_messages()
        full_text = ""
        for chunk in self.llm.chat_stream(messages):
            yield chunk.delta
            full_text += chunk.delta
        self.context.add_assistant_message(full_text)
        self.context.clear_tool_results()

    # ---- 内部方法 ----

    def _call_llm(self, messages: list[Message]) -> Any:
        return self.llm.chat(messages)

    def _call_llm_with_tools(self, messages: list[Message], tools: list[dict]) -> Any:
        try:
            return self.llm.call_with_tools(messages, tools)
        except Exception as e:
            logger.exception(f"Function calling not available: {e}")
            return self.llm.chat(messages)

    def _parse_response(self, response: Any) -> tuple[str, list[dict]]:
        content = ""
        tool_calls = []

        if hasattr(response, "content") and not hasattr(response, "choices"):
            for block in response.content:
                if block.type == "text":
                    content += block.text
                elif block.type == "tool_use":
                    tool_calls.append(
                        {
                            "id": getattr(block, "id", ""),
                            "name": block.name,
                            "arguments": dict(block.input)
                            if hasattr(block, "input") and block.input
                            else {},
                        }
                    )
            return content, tool_calls

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
                    tool_calls.append(
                        {
                            "id": getattr(tc, "id", ""),
                            "name": tc.function.name,
                            "arguments": args,
                        }
                    )
            return content, tool_calls

        content = str(response)
        return content, tool_calls

    def _execute_tool_call(self, tool_call: dict) -> str:
        name = tool_call["name"]
        args = tool_call.get("arguments", {})
        logger.info(f"Executing tool: {name}({args})")
        if self.tool_executor is None:
            return "错误：工具执行器未初始化"
        return self.tool_executor.registry.call(name, args)

    def clear(self) -> None:
        self.context.clear_history()
