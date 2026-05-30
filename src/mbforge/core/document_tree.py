"""文档结构树索引 — 参考 PageIndex 思想.

以文档原生章节结构（heading 层级）为唯一分块单元，取代固定长度 chunk。
向量检索、Agent 导航、页码精读全部基于同一套 section 数据。
"""

from __future__ import annotations

import copy
import dataclasses
import re
from pathlib import Path
from typing import Any

from ..utils.constants import PROJECT_META_DIR
from ..utils.helpers import load_json, save_json
from ..utils.logger import get_logger

logger = get_logger(__name__)


@dataclasses.dataclass
class SectionChunk:
    """文档章节片段 — 向量化/检索的唯一单元."""

    title: str = ""               # section 标题
    path: str = ""                # 层级路径，如 "1.Introduction > 1.1.Background"
    text: str = ""                # 完整正文（含 heading）
    page_start: int | None = None
    page_end: int | None = None
    line_start: int = 0
    line_end: int = 0


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


def _line_to_page(line_num: int, page_texts: list[str] | None) -> int | None:
    """将全文行号映射到页码（1-indexed）."""
    if not page_texts:
        return None
    cumulative = 0
    for page_idx, pt in enumerate(page_texts, start=1):
        page_lines = pt.count("\n") + 1
        if cumulative + page_lines >= line_num:
            return page_idx
        cumulative += page_lines + 2  # +2 for "\n\n" separator between pages
    return len(page_texts)


def _build_path(headings: list[dict[str, Any]], idx: int) -> str:
    """构建第 idx 个 heading 的层级路径."""
    h = headings[idx]
    level = h["level"]
    # 向前找同层级的前缀
    path_parts = [h["title"]]
    parent_level = level
    for j in range(idx - 1, -1, -1):
        prev = headings[j]
        if prev["level"] < parent_level:
            path_parts.insert(0, prev["title"])
            parent_level = prev["level"]
            if parent_level == 1:
                break
    return " > ".join(path_parts)


def _extract_section_texts(
    text: str, headings: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """根据 heading 列表提取每个 section 的文本范围和内容.

    参考 PageIndex page_index_md.py 的 extract_node_text_content。
    """
    lines = text.split("\n")
    sections = []
    for i, h in enumerate(headings):
        start_line = h["line_num"] - 1  # 0-indexed
        if i + 1 < len(headings):
            end_line = headings[i + 1]["line_num"] - 1
        else:
            end_line = len(lines)
        section_text = "\n".join(lines[start_line:end_line]).strip()
        if section_text:
            sections.append(
                {
                    "title": h["title"],
                    "level": h["level"],
                    "line_start": h["line_num"],
                    "line_end": end_line,
                    "text": section_text,
                }
            )
    return sections


def _split_long_section(
    section: dict[str, Any], path: str, max_chars: int
) -> list[SectionChunk]:
    """当 section 超过 max_chars 时，按段落再切分."""
    text = section["text"]
    if len(text) <= max_chars:
        return [
            SectionChunk(
                title=section["title"],
                path=path,
                text=text,
                line_start=section["line_start"],
                line_end=section["line_end"],
            )
        ]

    parts = text.split("\n\n")
    chunks: list[SectionChunk] = []
    current_text = ""
    part_idx = 0

    for part in parts:
        if not current_text:
            current_text = part
        elif len(current_text) + len(part) + 2 > max_chars:
            part_idx += 1
            chunks.append(
                SectionChunk(
                    title=section["title"],
                    path=f"{path} > part_{part_idx}",
                    text=current_text.strip(),
                    line_start=section["line_start"],
                    line_end=section["line_end"],
                )
            )
            current_text = part
        else:
            current_text += "\n\n" + part

    if current_text.strip():
        part_idx += 1
        chunks.append(
            SectionChunk(
                title=section["title"],
                path=f"{path} > part_{part_idx}" if chunks else path,
                text=current_text.strip(),
                line_start=section["line_start"],
                line_end=section["line_end"],
            )
        )
    return chunks


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
    """返回树的副本，移除 text 字段以节省 LLM token."""
    result = []
    for node in tree:
        cleaned = {k: v for k, v in node.items() if k != "text"}
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

    职责：
    1. 从 heading 生成 SectionChunk（唯一分块单元）
    2. 保存结构树和按页原文
    3. 提供结构导航 + 页码取文（Agent 辅助精读）
    """

    def __init__(self, project_root: Path):
        self.project_root = Path(project_root).resolve()
        self.meta_dir = self.project_root / PROJECT_META_DIR
        self.index_path = self.meta_dir / "doc_trees.json"
        self.pages_dir = self.meta_dir / "pages"
        self._trees: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        data = load_json(self.index_path)
        if data is not None:
            self._trees = data

    def save(self) -> None:
        save_json(self.index_path, self._trees)

    # ── 静态/类方法：不依赖 project_root，可在 DocumentProcessor 中调用 ──

    @staticmethod
    def build_sections(
        text: str,
        headings: list[dict[str, Any]],
        page_texts: list[str] | None = None,
        max_chars: int = 8000,
    ) -> list[SectionChunk]:
        """从文本和 heading 构建 section chunks（核心分块引擎）.

        Args:
            text: 文档全文
            headings: extract_headings() 的结果
            page_texts: 按页原文列表（用于计算 page_range）
            max_chars: 单 section 最大字符数，超过则按段落再切分
        """
        if not headings:
            # 无 heading 的文档：全文作为一个 section
            return [
                SectionChunk(
                    title="全文",
                    path="全文",
                    text=text,
                    page_start=_line_to_page(1, page_texts),
                    page_end=_line_to_page(text.count("\n") + 1, page_texts),
                    line_start=1,
                    line_end=text.count("\n") + 1,
                )
            ]

        raw_sections = _extract_section_texts(text, headings)
        sections: list[SectionChunk] = []

        for i, sec in enumerate(raw_sections):
            path = _build_path(headings, i)
            # 计算页码范围
            ps = _line_to_page(sec["line_start"], page_texts)
            pe = _line_to_page(sec["line_end"], page_texts)
            # 超长切分
            chunks = _split_long_section(sec, path, max_chars)
            for ck in chunks:
                ck.page_start = ps
                ck.page_end = pe
            sections.extend(chunks)

        return sections

    # ── 实例方法：依赖 project_root，用于持久化 ──

    def index_document(
        self,
        doc_id: str,
        sections: list[SectionChunk],
        page_count: int | None = None,
        page_texts: list[str] | None = None,
    ) -> None:
        """保存文档的树索引和按页原文."""
        # 从 sections 反推 headings 以构建树
        headings = []
        seen = set()
        for s in sections:
            key = (s.title, s.line_start)
            if key not in seen:
                seen.add(key)
                level = s.path.count(" > ") + 1
                headings.append({"level": level, "title": s.title, "line_num": s.line_start})
        headings.sort(key=lambda h: h["line_num"])
        tree = _build_tree(headings)

        self._trees[doc_id] = {
            "doc_id": doc_id,
            "page_count": page_count,
            "structure": tree,
        }
        self.save()

        if page_texts:
            doc_pages_dir = self.pages_dir / doc_id
            doc_pages_dir.mkdir(parents=True, exist_ok=True)
            for i, pt in enumerate(page_texts, start=1):
                (doc_pages_dir / f"page_{i}.txt").write_text(pt, encoding="utf-8")

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
                results.append(
                    {"page": p, "content": page_file.read_text(encoding="utf-8")}
                )
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
