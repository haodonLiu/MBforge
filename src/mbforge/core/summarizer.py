"""文档三层摘要机制（参考 OpenViking L0/L1/L2）.

- L0 Abstract:   ~100 tokens，一句话核心摘要，用于快速过滤
- L1 Overview:   ~2000 tokens，结构化概览，用于 Rerank 精排
- L2 Detail:     完整内容，按需加载

存储在项目 .mbforge/summaries/ 目录下。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from .document import ExtractedContent
from ..utils.constants import PROJECT_META_DIR
from ..utils.logger import get_logger

logger = get_logger(__name__)

SUMMARY_DIR = "summaries"


@dataclass
class DocumentSummary:
    """文档三层摘要."""

    doc_id: str
    l0_abstract: str = ""  # ~100 tokens
    l1_overview: str = ""  # ~2000 tokens
    l2_detail_hint: str = ""  # 指向完整内容的位置提示
    keywords: list[str] = None  # 关键词标签
    entity_tags: list[str] = None  # 实体标签（分子名、蛋白名等）

    def __post_init__(self):
        if self.keywords is None:
            self.keywords = []
        if self.entity_tags is None:
            self.entity_tags = []

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DocumentSummary:
        return cls(
            doc_id=data["doc_id"],
            l0_abstract=data.get("l0_abstract", ""),
            l1_overview=data.get("l1_overview", ""),
            l2_detail_hint=data.get("l2_detail_hint", ""),
            keywords=data.get("keywords", []),
            entity_tags=data.get("entity_tags", []),
        )


class SummaryManager:
    """项目级摘要管理器."""

    def __init__(self, project_root: Path):
        self.project_root = Path(project_root).resolve()
        self.summary_dir = self.project_root / PROJECT_META_DIR / SUMMARY_DIR
        self.summary_dir.mkdir(parents=True, exist_ok=True)

    def _summary_path(self, doc_id: str) -> Path:
        return self.summary_dir / f"{doc_id}.json"

    def save(self, summary: DocumentSummary) -> None:
        path = self._summary_path(summary.doc_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(summary.to_dict(), f, indent=2, ensure_ascii=False)

    def load(self, doc_id: str) -> DocumentSummary | None:
        path = self._summary_path(doc_id)
        if not path.exists():
            return None
        try:
            with open(path, encoding="utf-8") as f:
                return DocumentSummary.from_dict(json.load(f))
        except Exception as e:
            logger.warning(f"Failed to load summary for {doc_id}: {e}")
            return None

    def delete(self, doc_id: str) -> None:
        path = self._summary_path(doc_id)
        if path.exists():
            path.unlink()

    def list_all(self) -> list[DocumentSummary]:
        results = []
        for path in self.summary_dir.glob("*.json"):
            try:
                with open(path, encoding="utf-8") as f:
                    results.append(DocumentSummary.from_dict(json.load(f)))
            except Exception:
                pass
        return results


class DocumentSummarizer:
    """文档摘要生成器（依赖 LLM）."""

    def __init__(self, llm=None):
        self.llm = llm

    def summarize(self, content: ExtractedContent, doc_id: str) -> DocumentSummary:
        """为文档生成三层摘要."""
        text = content.text
        if not text:
            return DocumentSummary(doc_id=doc_id)

        # L0: 一句话摘要（如果 LLM 可用）
        l0 = self._generate_l0(text) if self.llm else text[:200]

        # L1: 结构化概览
        l1 = self._generate_l1(text) if self.llm else text[:2000]

        # 关键词提取（简单策略：前 10 个高频词）
        keywords = self._extract_keywords(text)

        # 实体标签（从分子数据中提取）
        entity_tags = [m.get("name", "") for m in content.molecules if m.get("name")]

        return DocumentSummary(
            doc_id=doc_id,
            l0_abstract=l0,
            l1_overview=l1,
            l2_detail_hint=f"Full text: {len(text)} chars, {len(content.chunks)} chunks",
            keywords=keywords,
            entity_tags=entity_tags,
        )

    def _generate_l0(self, text: str) -> str:
        """生成 L0 一句话摘要."""
        if self.llm is None:
            return text[:200]
        try:
            from ..models.base import Message

            prompt = f"请用一句话（不超过 80 字）总结以下科学文献的核心内容：\n\n{text[:4000]}"
            msgs = [
                Message(role="system", content="你是一位文献摘要专家。"),
                Message(role="user", content=prompt),
            ]
            return self.llm.chat(msgs).strip()
        except Exception as e:
            logger.warning(f"L0 generation failed: {e}")
            return text[:200]

    def _generate_l1(self, text: str) -> str:
        """生成 L1 结构化概览."""
        if self.llm is None:
            return text[:2000]
        try:
            from ..models.base import Message

            prompt = (
                "请对以下科学文献生成结构化概览（不超过 1500 字），包含：\n"
                "1. 研究背景与目的\n"
                "2. 主要方法与实验设计\n"
                "3. 关键结果与发现\n"
                "4. 涉及的分子/化合物列表\n"
                "5. 生物活性数据摘要\n\n"
                f"内容：\n{text[:4000]}"
            )
            msgs = [
                Message(role="system", content="你是一位专业的药物化学文献分析助手。"),
                Message(role="user", content=prompt),
            ]
            return self.llm.chat(msgs).strip()
        except Exception as e:
            logger.warning(f"L1 generation failed: {e}")
            return text[:2000]

    def _extract_keywords(self, text: str) -> list[str]:
        """简单关键词提取（按空格分词后统计频率）."""
        import re
        from collections import Counter

        # 提取 2-4 个字的词（中文）或 3-10 字符的英文词组
        words = re.findall(r"[a-zA-Z]{3,10}", text.lower())
        # 过滤常见停用词
        stop = {
            "the",
            "and",
            "for",
            "are",
            "but",
            "not",
            "you",
            "all",
            "can",
            "had",
            "her",
            "was",
            "one",
            "our",
            "out",
            "day",
            "get",
            "has",
            "him",
            "his",
            "how",
            "man",
            "new",
            "now",
            "old",
            "see",
            "two",
            "way",
            "who",
            "boy",
            "did",
            "its",
            "let",
            "put",
            "say",
            "she",
            "too",
            "use",
            "with",
            "that",
            "this",
            "from",
            "they",
            "have",
            "been",
            "were",
            "said",
            "each",
            "which",
            "their",
            "time",
            "will",
            "about",
            "would",
            "there",
            "could",
            "other",
            "after",
            "first",
            "these",
            "them",
            "some",
            "what",
            "when",
            "where",
            "than",
            "then",
            "more",
            "into",
            "over",
            "also",
            "only",
            "know",
            "take",
            "year",
            "good",
            "come",
            "make",
            "well",
            "work",
            "life",
            "even",
            "here",
            "look",
            "down",
            "most",
            "long",
            "last",
            "find",
            "give",
            "does",
            "made",
            "part",
            "such",
            "keep",
            "call",
            "came",
            "back",
            "much",
            "before",
            "right",
            "through",
            "during",
            "should",
            "between",
            "being",
            "both",
            "under",
            "never",
            "really",
            "still",
            "those",
            "while",
            "group",
            "high",
            "every",
            "great",
            "another",
            "study",
            "using",
            "used",
            "based",
            "shown",
            "showed",
            "results",
            "method",
            "activity",
            "compound",
            "molecular",
            "cell",
            "protein",
            "activity",
            "analysis",
            "data",
            "fig",
            "table",
            "et",
            "al",
            "vs",
        }
        filtered = [w for w in words if w not in stop and len(w) > 3]
        counter = Counter(filtered)
        return [w for w, _ in counter.most_common(10)]
