"""工具执行器.

将项目的实际能力（知识库搜索、分子查询等）封装为工具，供 Agent 调用。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from .tools import ToolMixin, ToolRegistry, tool
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
        project: Optional[Project] = None,
        knowledge_base: Optional[KnowledgeBase] = None,
        mol_db: Optional[MoleculeDatabase] = None,
    ):
        self.project = project
        self.kb = knowledge_base
        self.mol_db = mol_db
        self.registry = ToolRegistry()
        self._register_default_tools()

    def _register_default_tools(self) -> None:
        """注册默认工具集."""
        mixin = ToolMixin()

        # 知识库搜索
        mixin.register_from_function(self.registry, self.search_knowledge_base)
        mixin.register_from_function(self.registry, self.find_documents)
        mixin.register_from_function(self.registry, self.read_document_abstract)
        mixin.register_from_function(self.registry, self.read_document_overview)
        mixin.register_from_function(self.registry, self.read_document_detail)
        # 分子数据库
        mixin.register_from_function(self.registry, self.list_molecules)
        mixin.register_from_function(self.registry, self.search_molecule_by_smiles)
        # 文档列表
        mixin.register_from_function(self.registry, self.list_documents)
        mixin.register_from_function(self.registry, self.get_document_summary)
        # 项目信息
        mixin.register_from_function(self.registry, self.get_project_info)

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
        try:
            results = self.kb.search(query, top_k=top_k)
            if not results:
                return "未找到相关结果"
            lines = []
            for i, r in enumerate(results, 1):
                text = r["text"].replace("\n", " ")[:300]
                lines.append(f"{i}. {text}...")
            return "\n\n".join(lines)
        except Exception as e:
            logger.exception("KB search failed")
            return f"搜索失败: {e}"

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

            sm = SummaryManager(self.project.root)
            summaries = sm.list_all()

            # 先用 L0 摘要过滤
            matched = []
            for s in summaries:
                if keyword.lower() in s.l0_abstract.lower():
                    matched.append(s)
                    continue
                if keyword.lower() in " ".join(s.keywords).lower():
                    matched.append(s)
                    continue
                if keyword.lower() in " ".join(s.entity_tags).lower():
                    matched.append(s)

            if not matched:
                # fallback: 知识库搜索
                return self.search_knowledge_base(keyword, top_k=top_k)

            lines = [f"找到 {len(matched)} 个相关文档（按 L0 摘要过滤）:"]
            for s in matched[:top_k]:
                lines.append(f"- {s.doc_id}: {s.l0_abstract[:120]}...")
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
                act = f"{rec.activity} {rec.activity_type}" if rec.activity else "无活性数据"
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
            props = ", ".join([f"{k}={v:.2f}" for k, v in rec.properties.items()]) if rec.properties else "无"
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
                idx_mark = "✓" if d.indexed else "○"
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
            stats.append(f"分子总数: {mstats['total']}（含活性数据: {mstats['with_activity']}）")
        return "\n".join(stats)
