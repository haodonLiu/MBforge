"""项目级对话记忆持久化.

每个项目独立存储对话上下文，保存在 `.mbforge/memory/` 目录下。
`core/memory.py` 只负责字典的读写，序列化由调用方负责。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..utils.constants import MEMORY_DIR, PROJECT_META_DIR
from ..utils.logger import get_logger

logger = get_logger(__name__)

MEMORY_FILE = "conversation.json"


class ProjectMemory:
    """项目对话记忆管理器 — 只处理字典读写，不依赖 agent 模块."""

    def __init__(self, project_root: Path):
        self.project_root = Path(project_root).resolve()
        self.memory_dir = self.project_root / PROJECT_META_DIR / MEMORY_DIR
        self.memory_path = self.memory_dir / MEMORY_FILE
        self.memory_dir.mkdir(parents=True, exist_ok=True)

    def save_dict(self, data: dict[str, Any]) -> None:
        """保存对话上下文字典到磁盘."""
        try:
            with open(self.memory_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.debug(f"Conversation memory saved to {self.memory_path}")
        except Exception as e:
            logger.warning(f"Failed to save conversation memory: {e}")

    def load_dict(self) -> dict[str, Any] | None:
        """从磁盘加载对话上下文字典."""
        if not self.memory_path.exists():
            return None
        try:
            with open(self.memory_path, encoding="utf-8") as f:
                data = json.load(f)
            logger.info("Conversation memory loaded")
            return data
        except Exception as e:
            logger.warning(f"Failed to load conversation memory: {e}")
            return None

    def clear(self) -> None:
        """清空对话记忆."""
        if self.memory_path.exists():
            self.memory_path.unlink()
            logger.info("Conversation memory cleared")
