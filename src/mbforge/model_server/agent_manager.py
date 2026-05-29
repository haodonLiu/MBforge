"""全局 Agent 管理器.

Agent 实例全局持久化，workspace 随项目切换。
注意：记忆管理和上下文持久化已迁移到 Rust 端。
Python 端仅保留 Agent 初始化和工具执行桥接。
"""

from __future__ import annotations

import json
from pathlib import Path

from ..agent.agent import ProjectAgent
from ..agent.context import LayeredContext
from ..agent.executor import ToolExecutor
from ..agent.optimizations import OptimizationConfig, SemanticCache
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


def get_agent() -> ProjectAgent:
    """获取全局 Agent 实例."""
    global _agent
    if _agent is None:
        _agent = ProjectAgent(llm=get_llm(None))
    return _agent


def switch_project(project_root: str) -> None:
    """切换 Agent 的 workspace 到指定项目."""
    global _agent, _current_project_root

    if project_root == _current_project_root:
        return

    agent = get_agent()

    project = Project.open(Path(project_root)) if project_root else None

    if project is not None:
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

            # 初始化优化模块
            try:
                opt_config = OptimizationConfig()
                cache = SemanticCache(
                    project.root, embedder=embedder, config=opt_config.semantic_cache
                )
                cache.prefetch_hot_queries()
                tool_executor.set_semantic_cache(cache)
                tool_executor.enable_streaming_search(opt_config.streaming_search.enabled)
                if agent.sps_scheduler is not None:
                    agent.sps_scheduler.config = opt_config.sps
            except Exception as e:
                logger.debug("Optimization init skipped: %s", e)

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


def chat(user_input: str, project_root: str = "", messages: list[dict] | None = None) -> str:
    """与 Agent 对话."""
    if project_root:
        switch_project(project_root)

    agent = get_agent()

    if messages:
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "user":
                agent.context.add_user_message(content)
            elif role == "assistant":
                agent.context.add_assistant_message(content)

    return agent.chat(user_input)


def chat_stream(user_input: str, project_root: str = "", messages: list[dict] | None = None):
    """流式对话."""
    if project_root:
        switch_project(project_root)

    agent = get_agent()

    if messages:
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "user":
                agent.context.add_user_message(content)
            elif role == "assistant":
                agent.context.add_assistant_message(content)

    for chunk in agent.chat_stream(user_input):
        yield chunk


def get_tool_executor(project_root: str = "") -> ToolExecutor | None:
    """获取当前项目的 ToolExecutor 实例."""
    if project_root:
        switch_project(project_root)
    agent = get_agent()
    return agent.tool_executor
