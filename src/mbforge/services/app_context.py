"""AppContext — 应用资源生命周期管理.

集中管理 LLM、Embedder、Reranker、VLM、KnowledgeBase、MoleculeDatabase
等资源的创建、持有和释放，UI 层只消费 AppContext，不直接创建资源。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from ..core.knowledge_base import KnowledgeBase
from ..core.mol_database import MoleculeDatabase
from ..core.project import Project
from ..core.todo_manager import TodoManager
from ..models.base import BaseLLM, BaseEmbedder, BaseReranker, BaseVLM
from ..models.llm import create_llm_from_config
from ..models.embedding import create_embedder_from_config
from ..models.rerank import create_reranker_from_config
from ..parsers.pdf_parser import PDFParserPipeline
from ..utils.config import load_global_config

logger = logging.getLogger(__name__)


class AppContext:
    """应用级资源容器.

    职责：
    - 持有全局模型实例（LLM, Embedder, Reranker, VLM）
    - 管理项目级资源（KnowledgeBase, MoleculeDatabase, TodoManager, PDFPipeline）
    - 提供统一的初始化和释放接口

    UI 层通过 AppContext 访问所有资源，无需知道资源的创建细节。
    """

    def __init__(self):
        # 全局模型（跨项目共享）
        self.llm: Optional[BaseLLM] = None
        self.embedder: Optional[BaseEmbedder] = None
        self.reranker: Optional[BaseReranker] = None
        self.vlm: Optional[BaseVLM] = None

        # 项目级资源（随项目切换）
        self.project: Optional[Project] = None
        self.kb: Optional[KnowledgeBase] = None
        self.mol_db: Optional[MoleculeDatabase] = None
        self.todo_manager: Optional[TodoManager] = None
        self.pdf_pipeline: Optional[PDFParserPipeline] = None

    def init_models(self) -> None:
        """从全局配置初始化模型实例。"""
        config = load_global_config()
        try:
            self.embedder = create_embedder_from_config(config.embed)
        except Exception as e:
            logger.warning(f"Embedder init failed: {e}")
        try:
            self.llm = create_llm_from_config(config.llm)
            logger.info(f"LLM initialized: {type(self.llm).__name__}")
        except Exception as e:
            logger.warning(f"LLM init failed: {e}")
        try:
            self.reranker = create_reranker_from_config(config.rerank)
        except Exception as e:
            logger.warning(f"Reranker init failed: {e}")

    def open_project(self, project: Project) -> None:
        """打开项目，初始化项目级资源。"""
        self.close_project()

        self.project = project
        self.kb = KnowledgeBase(project.root, embedder=self.embedder)
        self.mol_db = MoleculeDatabase(project.root)
        self.todo_manager = TodoManager(project.root)
        self.pdf_pipeline = PDFParserPipeline(
            llm=self.llm,
            embedder=self.embedder,
            vlm=self.vlm,
            knowledge_base=self.kb,
            mol_db=self.mol_db,
        )
        logger.info(f"Project opened: {project.name}")

    def close_project(self) -> None:
        """释放项目级资源。"""
        if self.kb is not None:
            self.kb.close()
            self.kb = None
        if self.mol_db is not None:
            self.mol_db.close()
            self.mol_db = None
        self.todo_manager = None
        self.pdf_pipeline = None
        self.project = None

    def reload_models(self) -> None:
        """重新加载模型（设置变更后调用）。

        注意：会先关闭当前项目，调用方需重新 open_project()。
        """
        self.close_project()
        self.init_models()
