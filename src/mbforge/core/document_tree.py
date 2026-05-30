"""文档结构树索引 — 参考 PageIndex 思想.

不做 chunking，用文档原生章节结构（heading 层级）导航。
Agent 通过 get_doc_structure + get_doc_pages 实现"翻书"检索。
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

from ..utils.constants import PROJECT_META_DIR
from ..utils.logger import get_logger

logger = get_logger(__name__)


def extract_headings(text: str) -> list[dict[str, Any]]:
    """从文本提取 heading 层级（参考 PageIndex extract_nodes_from_markdown）."""
    pattern = r"^(#{1,6})\s+(.+)$"
    headings = []
    for line_num, line in enumerate(text.split("\n"), 1):
        stripped = line.strip()
        match = re.match(pattern, stripped)
        if match:
            level = len(match.group(1))
            title = match.group(2).strip()
            headings.append({"level": level, "title": title, "line_num": line_num})
    return headings


def _build_tree(headings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """从扁平 heading 列表构建嵌套树（参考 PageIndex build_tree_from_nodes）."""
    stack: list[tuple[dict[str, Any], int]] = []
    roots: list[dict[str, Any]] = []
    node_id = 1
    for h in headings:
        level = h["level"]
        node = {
            "title": h["title"],
            "node_id": f"{node_id:04d}",
            "line_num": h.get("line_num"),
            "nodes": [],
        }
        node_id += 1
        while stack and stack[-1][1] >= level:
            stack.pop()
        if not stack:
            roots.append(node)
        else:
            stack[-1][0]["nodes"].append(node)
        stack.append((node, level))
    return roots


def _strip_text_fields(tree: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """返回树的副本，移除 text 字段以节省 LLM token（参考 PageIndex remove_fields）."""
    result = []
    for node in tree:
        cleaned = {
            k: v for k, v in node.items() if k != "text"
        }
        if node.get("nodes"):
            cleaned["nodes"] = _strip_text_fields(node["nodes"])
        result.append(cleaned)
    return result


def _parse_pages(pages_str: str) -> list[int]:
    """解析页码字符串: '5-7', '3,8', '12' → [5,6,7,3,8,12]."""
    result = []
    for part in pages_str.split(","):
        part = part.strip()
        if "-" in part:
            start, end = map(int, part.split("-", 1))
            result.extend(range(start, end + 1))
        else:
            result.append(int(part))
    return sorted(set(result))


class DocumentTreeIndex:
    """文档结构树索引.

    为每个文档维护一棵 heading 树，支持:
    - 结构导航: get_structure(doc_id) → 树（不含正文）
    - 页码取文: get_pages(doc_id, page_nums) → 原文内容
    """

    def __init__(self, project_root: Path):
        self.project_root = Path(project_root).resolve()
        self.meta_dir = self.project_root / PROJECT_META_DIR
        self.index_path = self.meta_dir / "doc_trees.json"
        self.pages_dir = self.meta_dir / "pages"
        self._trees: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if self.index_path.exists():
            try:
                with open(self.index_path, encoding="utf-8") as f:
                    self._trees = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load doc tree index: {e}")

    def save(self) -> None:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.index_path, "w", encoding="utf-8") as f:
            json.dump(self._trees, f, indent=2, ensure_ascii=False)

    def index_document(
        self,
        doc_id: str,
        headings: list[dict[str, Any]],
        page_count: int | None = None,
        page_texts: list[str] | None = None,
    ) -> None:
        """为文档建立结构树索引，并可选保存按页原文."""
        tree = _build_tree(headings)
        self._trees[doc_id] = {
            "doc_id": doc_id,
            "page_count": page_count,
            "structure": tree,
        }
        self.save()

        # 保存按页原文（如有）
        if page_texts:
            doc_pages_dir = self.pages_dir / doc_id
            doc_pages_dir.mkdir(parents=True, exist_ok=True)
            for i, text in enumerate(page_texts, start=1):
                (doc_pages_dir / f"page_{i}.txt").write_text(
                    text, encoding="utf-8"
                )

    def remove_document(self, doc_id: str) -> None:
        """移除文档的树索引和页缓存."""
        self._trees.pop(doc_id, None)
        self.save()
        import shutil
        doc_pages_dir = self.pages_dir / doc_id
        if doc_pages_dir.exists():
            shutil.rmtree(doc_pages_dir)

    def get_structure(self, doc_id: str) -> list[dict[str, Any]] | None:
        """获取文档结构树（不含正文，省 token）."""
        doc = self._trees.get(doc_id)
        if not doc:
            return None
        return _strip_text_fields(doc.get("structure", []))

    def get_pages(self, doc_id: str, pages_str: str) -> list[dict[str, str]]:
        """按页码获取文档原文内容."""
        doc_pages_dir = self.pages_dir / doc_id
        if not doc_pages_dir.exists():
            return []
        try:
            page_nums = _parse_pages(pages_str)
        except ValueError as e:
            logger.warning(f"Invalid pages format '{pages_str}': {e}")
            return []

        results = []
        for p in page_nums:
            page_file = doc_pages_dir / f"page_{p}.txt"
            if page_file.exists():
                results.append({"page": p, "content": page_file.read_text(encoding="utf-8")})
        return results

    def get_doc_metadata(self, doc_id: str) -> dict[str, Any] | None:
        """获取文档树级元数据."""
        doc = self._trees.get(doc_id)
        if not doc:
            return None
        return {
            "doc_id": doc_id,
            "page_count": doc.get("page_count"),
            "section_count": len(doc.get("structure", [])),
        }
