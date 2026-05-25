"""记忆管理器（参考 OpenViking 6 类记忆 + TencentDB 记忆迭代）.

6 类记忆分类：
- profile:     用户基本信息
- preferences: 用户偏好（按主题）
- entities:    实体记忆（分子、蛋白、项目）
- events:      事件记录（决策、里程碑）
- cases:       Agent 学习案例
- patterns:    Agent 学习模式

存储在项目 .mbforge/memory/ 目录下。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from ..utils.constants import MEMORY_DIR, PROJECT_META_DIR
from ..utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class MemoryEntry:
    """单条记忆条目."""

    category: str  # profile | preferences | entities | events | cases | patterns
    key: str  # 记忆键（如 "user_name", "preferred_model"）
    content: str  # 记忆内容
    confidence: float = 1.0  # 置信度 0-1
    source: str = ""  # 来源（如 "conversation:msg_id"）
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    access_count: int = 0  # 被检索次数

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryEntry:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class MemoryManager:
    """项目级记忆管理器."""

    CATEGORIES = ["profile", "preferences", "entities", "events", "cases", "patterns"]

    def __init__(self, project_root: Path):
        self.project_root = Path(project_root).resolve()
        self.memory_dir = self.project_root / PROJECT_META_DIR / MEMORY_DIR
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, list[MemoryEntry]] = {}
        self._load_all()

    def _category_path(self, category: str) -> Path:
        return self.memory_dir / f"{category}.json"

    def _load_all(self) -> None:
        """加载所有记忆到缓存."""
        for cat in self.CATEGORIES:
            path = self._category_path(cat)
            if path.exists():
                try:
                    with open(path, encoding="utf-8") as f:
                        data = json.load(f)
                    self._cache[cat] = [MemoryEntry.from_dict(e) for e in data]
                except Exception as e:
                    logger.warning(f"Failed to load memory category {cat}: {e}")
                    self._cache[cat] = []
            else:
                self._cache[cat] = []

    def _save_category(self, category: str) -> None:
        """保存单类记忆."""
        path = self._category_path(category)
        try:
            entries = self._cache.get(category, [])
            with open(path, "w", encoding="utf-8") as f:
                json.dump(
                    [e.to_dict() for e in entries], f, indent=2, ensure_ascii=False
                )
        except Exception as e:
            logger.warning(f"Failed to save memory category {category}: {e}")

    def add(
        self,
        category: str,
        key: str,
        content: str,
        confidence: float = 1.0,
        source: str = "",
    ) -> None:
        """添加或更新记忆."""
        if category not in self.CATEGORIES:
            logger.warning(f"Unknown memory category: {category}")
            return

        entries = self._cache.setdefault(category, [])
        # 查找是否已存在
        for e in entries:
            if e.key == key:
                e.content = content
                e.confidence = confidence
                e.source = source
                e.updated_at = datetime.now().isoformat()
                self._save_category(category)
                return

        # 新建
        entries.append(
            MemoryEntry(
                category=category,
                key=key,
                content=content,
                confidence=confidence,
                source=source,
            )
        )
        self._save_category(category)
        logger.info(f"Memory added: {category}/{key}")

    def get(self, category: str, key: str) -> MemoryEntry | None:
        """获取单条记忆."""
        for e in self._cache.get(category, []):
            if e.key == key:
                e.access_count += 1
                return e
        return None

    def search(self, category: str, query: str) -> list[MemoryEntry]:
        """在指定类别中搜索记忆（简单子串匹配）."""
        results = []
        for e in self._cache.get(category, []):
            if query.lower() in e.content.lower() or query.lower() in e.key.lower():
                e.access_count += 1
                results.append(e)
        return results

    def list_category(self, category: str) -> list[MemoryEntry]:
        """列出某类全部记忆."""
        return list(self._cache.get(category, []))

    def delete(self, category: str, key: str) -> bool:
        """删除记忆."""
        entries = self._cache.get(category, [])
        for i, e in enumerate(entries):
            if e.key == key:
                entries.pop(i)
                self._save_category(category)
                return True
        return False

    def get_user_profile_text(self) -> str:
        """获取用户画像文本（用于注入 LLM 上下文）."""
        lines = []
        for cat in ["profile", "preferences", "entities"]:
            entries = self._cache.get(cat, [])
            if entries:
                lines.append(f"[{cat}]")
                for e in entries:
                    lines.append(f"  {e.key}: {e.content}")
        return "\n".join(lines) if lines else ""

    def get_agent_memory_text(self) -> str:
        """获取 Agent 学习记忆文本."""
        lines = []
        for cat in ["cases", "patterns"]:
            entries = self._cache.get(cat, [])
            if entries:
                lines.append(f"[{cat}]")
                for e in entries:
                    lines.append(f"  {e.key}: {e.content}")
        return "\n".join(lines) if lines else ""

    def extract_from_conversation(self, messages: list, llm=None) -> None:
        """从对话历史中自动提取记忆（记忆自迭代）.

        需要 LLM 来分析对话，提取有价值的记忆。
        """
        if llm is None or len(messages) < 2:
            return

        try:
            from ..models.base import Message

            conversation = "\n".join(
                [f"{m.role}: {m.content[:500]}" for m in messages[-10:]]
            )
            prompt = (
                "请分析以下对话，提取有价值的记忆条目。按 JSON 数组格式输出，每个条目包含：\n"
                "- category: profile/preferences/entities/events/cases/patterns\n"
                "- key: 简短的键名\n"
                "- content: 具体内容\n"
                "- confidence: 0.0-1.0\n\n"
                "只输出 JSON 数组，不要其他说明。\n\n"
                f"对话：\n{conversation}"
            )
            response = llm.chat(
                [
                    Message(role="system", content="你是一位记忆提取专家。"),
                    Message(role="user", content=prompt),
                ]
            )

            # 尝试解析 JSON
            import re

            json_match = re.search(r"\[.*\]", response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
                for item in data:
                    cat = item.get("category", "")
                    if cat in self.CATEGORIES:
                        self.add(
                            category=cat,
                            key=item.get("key", "unknown"),
                            content=item.get("content", ""),
                            confidence=item.get("confidence", 0.5),
                            source="auto_extraction",
                        )
        except Exception as e:
            logger.warning(f"Memory extraction failed: {e}")
