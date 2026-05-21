"""检索轨迹记录器（参考 OpenViking 轨迹可视化）.

记录 Agent 的每一步检索行为，形成可追溯的 "viking://" 路径。
用于：
- 结果可解释性
- 检索策略优化
- Agent 模式学习
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..utils.constants import PROJECT_META_DIR, TRAJECTORY_DIR, TRAJECTORY_FILE, VIKING_SCHEME
from ..utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class TrajectoryStep:
    """单步检索/操作记录."""

    step_type: str          # "search" | "navigate" | "read" | "abstract" | "overview" | "tool"
    uri: str                # viking:// 风格路径，如 "viking://kb/search?q=foo"
    query: str = ""         # 原始查询
    result_count: int = 0   # 返回结果数
    top_results: List[str] = field(default_factory=list)  # 结果摘要
    duration_ms: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TrajectoryStep:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class TrajectoryTracker:
    """检索轨迹跟踪器."""

    def __init__(self, project_root: Path):
        self.project_root = Path(project_root).resolve()
        self.trajectory_path = self.project_root / PROJECT_META_DIR / TRAJECTORY_DIR / TRAJECTORY_FILE
        self.trajectory_path.parent.mkdir(parents=True, exist_ok=True)
        self._steps: List[TrajectoryStep] = []
        self._load()

    def _load(self) -> None:
        if self.trajectory_path.exists():
            try:
                with open(self.trajectory_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._steps = [TrajectoryStep.from_dict(s) for s in data.get("steps", [])]
            except Exception as e:
                logger.warning(f"Failed to load trajectory: {e}")
                self._steps = []

    def save(self) -> None:
        try:
            with open(self.trajectory_path, "w", encoding="utf-8") as f:
                json.dump({
                    "steps": [s.to_dict() for s in self._steps],
                    "updated_at": datetime.now().isoformat(),
                }, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Failed to save trajectory: {e}")

    def add_step(self, step: TrajectoryStep) -> None:
        self._steps.append(step)
        # 保留最近 500 步
        if len(self._steps) > 500:
            self._steps = self._steps[-500:]
        self.save()

    def record_search(
        self,
        query: str,
        result_count: int,
        top_results: List[str],
        duration_ms: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """记录一次搜索操作."""
        self.add_step(TrajectoryStep(
            step_type="search",
            uri=f"{VIKING_SCHEME}kb/search?q={query[:100]}",
            query=query,
            result_count=result_count,
            top_results=top_results[:5],
            duration_ms=duration_ms,
            metadata=metadata or {},
        ))

    def record_navigate(
        self,
        path: str,
        reason: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """记录一次目录/路径导航."""
        self.add_step(TrajectoryStep(
            step_type="navigate",
            uri=f"{VIKING_SCHEME}project/{path}",
            query=reason,
            metadata=metadata or {},
        ))

    def record_read(
        self,
        doc_id: str,
        level: str = "detail",  # abstract | overview | detail
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """记录一次文档读取."""
        self.add_step(TrajectoryStep(
            step_type="read",
            uri=f"{VIKING_SCHEME}docs/{doc_id}?level={level}",
            query=doc_id,
            metadata=metadata or {},
        ))

    def record_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        result_summary: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """记录一次工具调用."""
        self.add_step(TrajectoryStep(
            step_type="tool",
            uri=f"{VIKING_SCHEME}tools/{tool_name}",
            query=json.dumps(arguments, ensure_ascii=False)[:200],
            result_count=1 if result_summary else 0,
            top_results=[result_summary[:200]] if result_summary else [],
            metadata=metadata or {},
        ))

    def get_recent(self, limit: int = 10) -> List[TrajectoryStep]:
        return self._steps[-limit:]

    def get_summary(self) -> str:
        """获取轨迹摘要文本."""
        if not self._steps:
            return "无检索轨迹"
        lines = [f"检索轨迹（最近 {len(self._steps)} 步）:"]
        for s in self._steps[-10:]:
            lines.append(f"  [{s.step_type}] {s.uri} -> {s.result_count} results")
        return "\n".join(lines)

    def clear(self) -> None:
        self._steps.clear()
        if self.trajectory_path.exists():
            self.trajectory_path.unlink()
