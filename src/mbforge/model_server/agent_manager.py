"""工具执行器工厂 — Rust Agent 通过 HTTP 调用 Python 工具的桥梁.

Rust Agent 的 sidecar tools（search_knowledge_base, list_molecules 等）
需要调用 Python 端的 Project / KnowledgeBase / MoleculeDatabase。
此模块提供无状态的工具执行器创建和调用，不依赖任何 Agent 实例。
"""

from __future__ import annotations

from pathlib import Path

from ..agent.executor import ToolExecutor
from ..agent.optimizations import OptimizationConfig, SemanticCache
from ..core.project import Project
from ..core.knowledge_base import KnowledgeBase
from ..core.mol_database import MoleculeDatabase
from ..utils.logger import get_logger
from .models.embedder import get_embedder

logger = get_logger(__name__)

_cached_executors: dict[str, ToolExecutor] = {}


def get_tool_executor(project_root: str = "") -> ToolExecutor | None:
    """获取指定项目的 ToolExecutor 实例（缓存，按 project_root 隔离）."""
    if not project_root:
        return None

    if project_root in _cached_executors:
        return _cached_executors[project_root]

    try:
        root = Path(project_root)
        project = Project.open(root)
        if project is None:
            logger.warning("Failed to open project: %s", project_root)
            return None

        embedder = get_embedder()
        kb = KnowledgeBase(project.root, embedder=embedder)
        mol_db = MoleculeDatabase(project.root)
        executor = ToolExecutor(project=project, knowledge_base=kb, mol_db=mol_db)

        # Initialize optimization modules
        try:
            opt_config = OptimizationConfig()
            cache = SemanticCache(
                root, embedder=embedder, config=opt_config.semantic_cache
            )
            cache.prefetch_hot_queries()
            executor.set_semantic_cache(cache)
            executor.enable_streaming_search(opt_config.streaming_search.enabled)
        except Exception as e:
            # TODO-AUDIT: Optimization init failure is logged at debug level only.
            # Operator will not see this — system continues without semantic cache.
            logger.debug("Optimization init skipped: %s", e)

        _cached_executors[project_root] = executor
        logger.info("ToolExecutor created for project: %s", project_root)
        return executor
    except Exception as e:
        logger.exception("Failed to create ToolExecutor for %s", project_root)
        return None
