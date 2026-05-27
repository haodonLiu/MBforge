"""全局 Agent 管理器.

Agent 实例全局持久化，workspace 随项目切换。
上下文按 token 裁剪，支持持久化到本地文件。
"""

from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime

from ..agent.agent import ProjectAgent
from ..agent.context import LayeredContext
from ..agent.executor import ToolExecutor
from ..core.project import Project
from ..core.knowledge_base import KnowledgeBase
from ..core.mol_database import MoleculeDatabase
from ..utils.constants import PROJECT_META_DIR
from ..utils.logger import get_logger
from .models.llm import get_llm
from .models.embedder import get_embedder

logger = get_logger(__name__)

# 全局单例
_agent: ProjectAgent | None = None
_current_project_root: str = ""


def _get_context_path(project_root: str) -> Path:
    """获取上下文持久化路径."""
    return Path(project_root) / PROJECT_META_DIR / "memory" / "agent_context.json"


def get_agent() -> ProjectAgent:
    """获取全局 Agent 实例."""
    global _agent, _current_project_root
    if _agent is None:
        _agent = ProjectAgent(llm=get_llm(None))
    return _agent


def switch_project(project_root: str) -> None:
    """切换 Agent 的 workspace 到指定项目."""
    global _agent, _current_project_root

    if project_root == _current_project_root:
        return

    agent = get_agent()

    # 保存旧项目的上下文
    if _current_project_root:
        _save_context(_current_project_root, agent.context)

    project = Project.open(Path(project_root)) if project_root else None

    if project is not None:
        # 尝试加载已保存的上下文
        saved_context = _load_context(project_root)

        try:
            embedder = get_embedder()
            kb = KnowledgeBase(project.root, embedder=embedder)
            mol_db = MoleculeDatabase(project.root)
            tool_executor = ToolExecutor(
                project=project,
                knowledge_base=kb,
                mol_db=mol_db,
            )
            agent.tool_executor = tool_executor
            agent.project_root = project.root

            if saved_context:
                # 恢复已保存的上下文
                agent.context = saved_context
                agent._inject_tool_descriptions()
                logger.info(f"Restored context for project: {project_root}")
            else:
                # 新建上下文
                agent.context = LayeredContext(
                    system_prompt=agent.DEFAULT_SYSTEM_PROMPT,
                    max_history_rounds=20,
                    max_total_tokens=32000,
                )
                agent._inject_tool_descriptions()
        except Exception as e:
            logger.warning(f"Failed to initialize tools for project: {e}")
            agent.tool_executor = None
            agent.project_root = None
    else:
        agent.tool_executor = None
        agent.project_root = None
        agent.context = LayeredContext(
            system_prompt=agent.DEFAULT_SYSTEM_PROMPT,
            max_history_rounds=20,
            max_total_tokens=32000,
        )

    _current_project_root = project_root
    logger.info(f"Agent workspace switched to: {project_root}")


def _save_context(project_root: str, context: LayeredContext) -> None:
    """保存上下文到本地文件."""
    path = _get_context_path(project_root)
    context.save_to_file(path)


def _load_context(project_root: str) -> LayeredContext | None:
    """从本地文件加载上下文."""
    path = _get_context_path(project_root)
    return LayeredContext.load_from_file(path)


def get_chat_history_path(project_root: str) -> Path:
    """Get chat history file path."""
    return Path(project_root) / PROJECT_META_DIR / "memory" / "chat_history.json"


def load_chat_history(project_root: str) -> list[dict]:
    """Load chat history from disk."""
    path = get_chat_history_path(project_root)
    if not path.exists():
        return []
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_chat_history(project_root: str, messages: list[dict]) -> None:
    """Save chat history to disk."""
    path = get_chat_history_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)


def chat(user_input: str, project_root: str = "") -> str:
    """与 Agent 对话."""
    if project_root:
        switch_project(project_root)

    agent = get_agent()
    response = agent.chat(user_input)

    # 对话后保存上下文
    if _current_project_root:
        _save_context(_current_project_root, agent.context)

    return response


def chat_stream(user_input: str, project_root: str = ""):
    """流式对话."""
    if project_root:
        switch_project(project_root)

    agent = get_agent()
    full_response = ""
    for chunk in agent.chat_stream(user_input):
        full_response += chunk
        yield chunk

    # 对话后保存上下文
    if _current_project_root:
        _save_context(_current_project_root, agent.context)
