"""工具执行器.

将项目的实际能力（知识库搜索、分子查询等）封装为工具，供 Agent 调用。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .tools import ToolMixin, ToolRegistry, tool
from ..utils.helpers import truncate_text
from ..utils.logger import get_logger

if TYPE_CHECKING:
    from ..core.knowledge_base import KnowledgeBase
    from ..core.mol_database import MoleculeDatabase
    from ..core.project import Project

logger = get_logger(__name__)


class ToolExecutor:
    """项目工具执行器.

    将 Project / KnowledgeBase / MoleculeDatabase 的能力暴露为 LLM 可调用的工具。
    """

    def __init__(
        self,
        project: Project | None = None,
        knowledge_base: KnowledgeBase | None = None,
        mol_db: MoleculeDatabase | None = None,
    ):
        self.project = project
        self.kb = knowledge_base
        self.mol_db = mol_db
        self.semantic_cache: Any = None
        self.use_streaming_search: bool = False
        self.registry = ToolRegistry()
        self._register_default_tools()

    def set_semantic_cache(self, cache: Any) -> None:
        """设置语义缓存实例."""
        self.semantic_cache = cache

    def enable_streaming_search(self, enabled: bool = True) -> None:
        """启用/禁用流式搜索工具."""
        self.use_streaming_search = enabled

    def _register_default_tools(self) -> None:
        """注册默认工具集."""
        mixin = ToolMixin()

        # 知识库搜索
        mixin.register_from_function(self.registry, self.search_knowledge_base)
        mixin.register_from_function(self.registry, self.find_documents)
        mixin.register_from_function(self.registry, self.read_document_abstract)
        mixin.register_from_function(self.registry, self.read_document_overview)
        mixin.register_from_function(self.registry, self.read_document_detail)
        # 文档结构树导航（参考 PageIndex）
        mixin.register_from_function(self.registry, self.get_doc_structure)
        mixin.register_from_function(self.registry, self.get_doc_pages)
        # 分子数据库
        mixin.register_from_function(self.registry, self.list_molecules)
        mixin.register_from_function(self.registry, self.search_molecule_by_smiles)
        # 文档列表
        mixin.register_from_function(self.registry, self.list_documents)
        mixin.register_from_function(self.registry, self.get_document_summary)
        # 项目信息
        mixin.register_from_function(self.registry, self.get_project_info)

        # 流式搜索（条件注册）
        if self.use_streaming_search:
            mixin.register_from_function(self.registry, self.streaming_search_knowledge_base)

    # ---- 工具定义 ----

    @tool(
        "搜索项目知识库",
        {
            "query": {
                "type": "string",
                "description": "自然语言搜索查询，如'分子对接方法'",
            },
            "top_k": {
                "type": "integer",
                "description": "返回结果数量，默认5",
            },
        },
    )
    def search_knowledge_base(self, query: str, top_k: int = 5) -> str:
        """语义搜索项目知识库中的文档片段."""
        if self.kb is None:
            return "错误：知识库未初始化，请先打开项目"

        # 优先查缓存
        if self.semantic_cache is not None:
            cached = self.semantic_cache.get_l1(query)
            if cached is None:
                cached = self.semantic_cache.get_l2(query)
            if cached is not None:
                return self._format_search_results(cached, top_k)

        try:
            results = self.kb.search(query, top_k=top_k)
            if self.semantic_cache is not None and results:
                self.semantic_cache.store(query, results)
            if not results:
                return (
                    "知识库中未找到相关信息。"
                    "这可能是因为项目尚未索引文档，或查询内容不在已索引的文档中。"
                    "我将基于预训练知识回答您的问题。"
                )
            return self._format_search_results(results, top_k)
        except Exception as e:
            logger.exception("KB search failed")
            return f"搜索失败: {e}"

    @staticmethod
    def _format_search_results(results: list[dict], top_k: int) -> str:
        """格式化搜索结果为文本."""
        lines = []
        for i, r in enumerate(results[:top_k], 1):
            text = truncate_text(r["text"].replace("\n", " "), max_len=300)
            lines.append(f"{i}. {text}...")
        return "\n\n".join(lines)

    @tool(
        "按关键词或实体查找文档",
        {
            "keyword": {
                "type": "string",
                "description": "关键词或实体名，如 'aspirin' 或 'docking'",
            },
            "doc_type": {
                "type": "string",
                "description": "文档类型过滤: pdf, markdown, text。空字符串表示全部",
            },
            "top_k": {
                "type": "integer",
                "description": "返回结果数量，默认5",
            },
        },
    )
    def find_documents(self, keyword: str, doc_type: str = "", top_k: int = 5) -> str:
        """按关键词或实体名查找项目文档（支持 L0 摘要快速过滤）."""
        if self.project is None or self.kb is None:
            return "错误：项目或知识库未初始化"
        try:
            from ..core.summarizer import SummaryManager

            # 优先用知识库语义搜索，如果结果不足再加载摘要过滤
            candidates = self.kb.search(keyword, top_k=top_k * 3)
            candidate_ids = {r["metadata"].get("doc_id") for r in candidates}

            # 只加载命中的文档的摘要
            sm = SummaryManager(self.project.root)
            summaries = {
                s.doc_id: s for s in sm.list_all() if s.doc_id in candidate_ids
            }

            matched = []
            for doc_id in candidate_ids:
                s = summaries.get(doc_id)
                if s is None:
                    continue
                if keyword.lower() in s.l0_abstract.lower():
                    matched.append(s)
                    continue
                if keyword.lower() in " ".join(s.keywords).lower():
                    matched.append(s)
                    continue
                if keyword.lower() in " ".join(s.entity_tags).lower():
                    matched.append(s)

            if not matched:
                return self.search_knowledge_base(keyword, top_k=top_k)

            lines = [f"找到 {len(matched)} 个相关文档（按 L0 摘要过滤）:"]
            for s in matched[:top_k]:
                lines.append(f"- {s.doc_id}: {truncate_text(s.l0_abstract, 120)}")
                if s.entity_tags:
                    lines.append(f"  实体: {', '.join(s.entity_tags)}")
            return "\n".join(lines)
        except Exception as e:
            logger.exception("Find documents failed")
            return f"查找失败: {e}"

    @tool(
        "读取文档 L0 摘要",
        {
            "doc_id": {
                "type": "string",
                "description": "文档ID",
            },
        },
    )
    def read_document_abstract(self, doc_id: str) -> str:
        """读取文档的 L0 一句话摘要（快速了解文档核心内容）."""
        if self.kb is None:
            return "错误：知识库未初始化"
        try:
            abstract = self.kb.get_document_abstract(doc_id)
            if abstract:
                return f"[{doc_id}] L0 摘要:\n{abstract}"
            return f"文档 {doc_id} 暂无 L0 摘要"
        except Exception as e:
            return f"读取失败: {e}"

    @tool(
        "读取文档 L1 概览",
        {
            "doc_id": {
                "type": "string",
                "description": "文档ID",
            },
        },
    )
    def read_document_overview(self, doc_id: str) -> str:
        """读取文档的 L1 结构化概览（包含背景、方法、结果、分子列表）."""
        if self.kb is None:
            return "错误：知识库未初始化"
        try:
            overview = self.kb.get_document_overview(doc_id)
            if overview:
                return f"[{doc_id}] L1 概览:\n{overview}"
            return f"文档 {doc_id} 暂无 L1 概览"
        except Exception as e:
            return f"读取失败: {e}"

    @tool(
        "读取文档完整内容",
        {
            "doc_id": {
                "type": "string",
                "description": "文档ID",
            },
            "max_chars": {
                "type": "integer",
                "description": "最大字符数，默认4000",
            },
        },
    )
    def read_document_detail(self, doc_id: str, max_chars: int = 4000) -> str:
        """读取文档的完整内容片段（L2 Detail）."""
        if self.kb is None:
            return "错误：知识库未初始化"
        try:
            # 从知识库中获取该文档的 chunks
            results = self.kb.search("", top_k=20, filter_dict={"doc_id": doc_id})
            if not results:
                return f"文档 {doc_id} 暂无索引内容"
            texts = [r["text"] for r in results]
            full_text = "\n\n".join(texts)
            if len(full_text) > max_chars:
                full_text = full_text[:max_chars] + "\n...[内容已截断]"
            return f"[{doc_id}] 完整内容:\n{full_text}"
        except Exception as e:
            return f"读取失败: {e}"

    @tool(
        "列出分子数据库",
        {
            "limit": {
                "type": "integer",
                "description": "最多返回多少条记录，默认20",
            },
        },
    )
    def list_molecules(self, limit: int = 20) -> str:
        """列出项目分子数据库中的分子."""
        if self.mol_db is None:
            return "错误：分子数据库未初始化"
        try:
            records = self.mol_db.list_all(limit=limit)
            if not records:
                return "分子数据库为空"
            lines = []
            for rec in records:
                act = (
                    f"{rec.activity} {rec.activity_type}"
                    if rec.activity
                    else "无活性数据"
                )
                lines.append(f"- {rec.name or rec.smiles[:30]} | {act}")
            return f"共 {len(records)} 条分子记录:\n" + "\n".join(lines)
        except Exception as e:
            logger.exception("List molecules failed")
            return f"查询失败: {e}"

    @tool(
        "按SMILES搜索分子",
        {
            "smiles": {
                "type": "string",
                "description": "分子的SMILES字符串",
            },
        },
    )
    def search_molecule_by_smiles(self, smiles: str) -> str:
        """根据 SMILES 在分子数据库中查找分子."""
        if self.mol_db is None:
            return "错误：分子数据库未初始化"
        try:
            rec = self.mol_db.search_by_smiles(smiles)
            if rec is None:
                return f"未找到 SMILES 为 {smiles} 的分子"
            props = (
                ", ".join([f"{k}={v:.2f}" for k, v in rec.properties.items()])
                if rec.properties
                else "无"
            )
            return (
                f"名称: {rec.name or '-'}\n"
                f"SMILES: {rec.smiles}\n"
                f"活性: {rec.activity or '-'} {rec.activity_type} {rec.units}\n"
                f"性质: {props}\n"
                f"备注: {rec.notes or '-'}"
            )
        except Exception as e:
            return f"查询失败: {e}"

    @tool(
        "列出项目文档",
        {
            "doc_type": {
                "type": "string",
                "description": "文档类型过滤: pdf, markdown, text, molecule, data。空字符串表示全部",
            },
        },
    )
    def list_documents(self, doc_type: str = "") -> str:
        """列出项目中的文档文件."""
        if self.project is None:
            return "错误：未打开项目"
        try:
            docs = self.project.list_documents(doc_type=doc_type or None)
            if not docs:
                return "项目中暂无文档"
            lines = [f"共 {len(docs)} 个文件:"]
            for d in docs[:50]:
                idx_mark = "[x]" if d.indexed else "[ ]"
                lines.append(f"  {idx_mark} [{d.doc_type}] {d.path.name}")
            return "\n".join(lines)
        except Exception as e:
            return f"列出文档失败: {e}"

    @tool(
        "获取文档摘要",
        {
            "doc_id": {
                "type": "string",
                "description": "文档ID",
            },
        },
    )
    def get_document_summary(self, doc_id: str) -> str:
        """获取指定文档的摘要信息."""
        if self.project is None:
            return "错误：未打开项目"
        try:
            entry = self.project.get_document(doc_id)
            if entry is None:
                return f"未找到文档 {doc_id}"
            return (
                f"文件名: {entry.path.name}\n"
                f"类型: {entry.doc_type}\n"
                f"路径: {entry.path}\n"
                f"已索引: {'是' if entry.indexed else '否'}\n"
                f"哈希: {entry.hash[:16]}..."
            )
        except Exception as e:
            return f"获取摘要失败: {e}"

    @tool(
        "获取项目信息",
        {},
    )
    def get_project_info(self) -> str:
        """获取当前项目的基本信息."""
        if self.project is None:
            return "错误：未打开项目"
        stats = []
        stats.append(f"项目名称: {self.project.name}")
        stats.append(f"项目路径: {self.project.root}")
        docs = self.project.list_documents()
        stats.append(f"文档总数: {len(docs)}")
        if self.mol_db:
            mstats = self.mol_db.get_stats()
            stats.append(
                f"分子总数: {mstats['total']}（含活性数据: {mstats['with_activity']}）"
            )
        return "\n".join(stats)

    @tool(
        "获取文档结构树",
        {
            "doc_id": {
                "type": "string",
                "description": "文档ID",
            },
        },
    )
    def get_doc_structure(self, doc_id: str) -> str:
        """获取文档的章节树结构（不含正文），供 LLM 导航翻书用（参考 PageIndex）."""
        if self.kb is None:
            return "错误：知识库未初始化"
        try:
            import json as _json
            tree = self.kb._tree_index.get_structure(doc_id)
            if tree is None:
                return f"文档 {doc_id} 暂无结构树"
            meta = self.kb._tree_index.get_doc_metadata(doc_id)
            return (
                f"文档 {doc_id} 结构（共 {meta.get('section_count', 0)} 个顶层章节, "
                f"{meta.get('page_count', '?')} 页）:\n"
                + _json.dumps(tree, ensure_ascii=False, indent=2)
            )
        except Exception as e:
            return f"获取结构失败: {e}"

    @tool(
        "按页码获取文档内容",
        {
            "doc_id": {
                "type": "string",
                "description": "文档ID",
            },
            "pages": {
                "type": "string",
                "description": "页码，支持格式: '5-7', '3,8', '12'",
            },
        },
    )
    def get_doc_pages(self, doc_id: str, pages: str) -> str:
        """按页码获取文档原文内容，让 LLM 像翻书一样精确读取（参考 PageIndex retrieve.py）."""
        if self.kb is None:
            return "错误：知识库未初始化"
        try:
            results = self.kb._tree_index.get_pages(doc_id, pages)
            if not results:
                return f"文档 {doc_id} 未找到指定页码内容（页码格式: '5-7', '3,8'）"
            lines = []
            for r in results:
                content = r["content"].replace("\n", " ")[:800]
                lines.append(f"--- 第 {r['page']} 页 ---\n{content}")
            return "\n\n".join(lines)
        except Exception as e:
            return f"读取页内容失败: {e}"

    @tool(
        "流式搜索项目知识库",
        {
            "query": {
                "type": "string",
                "description": "自然语言搜索查询",
            },
            "top_k": {
                "type": "integer",
                "description": "返回结果数量，默认5",
            },
        },
    )
    def streaming_search_knowledge_base(self, query: str, top_k: int = 5) -> str:
        """流式语义搜索，前3条结果立即返回。"""
        if self.kb is None:
            return "错误：知识库未初始化"
        try:
            from .optimizations.stream_search import (
                StreamingKnowledgeBaseSearch,
                StreamingSearchConfig,
            )

            streamer = StreamingKnowledgeBaseSearch(
                self.kb, StreamingSearchConfig(enabled=True, yield_first=3)
            )
            first_results: list[dict] = []
            for batch in streamer.stream(query, top_k=top_k):
                if batch["type"] == "first":
                    first_results = batch["results"]
                elif batch["type"] == "complete":
                    break

            if not first_results:
                return "知识库中未找到相关信息。"
            return self._format_search_results(first_results, top_k)
        except Exception:
            logger.exception("Streaming KB search failed")
            return self.search_knowledge_base(query, top_k=top_k)
