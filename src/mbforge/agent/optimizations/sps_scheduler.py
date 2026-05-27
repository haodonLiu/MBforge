"""Speculative Parallel Scheduling (SPS) — 预测下一步工具调用并预执行."""

from __future__ import annotations

import re
import threading
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

from ...utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class SPSConfig:
    enabled: bool = True
    speculation_threshold: float = 0.6


class ToolCallPredictor:
    """基于频率统计的工具调用预测器。

    内置 domain knowledge fallback：search_knowledge_base 后
    默认预测 read_document_abstract / read_document_overview。
    """

    KB_SEARCH_NEXT = [
        "read_document_abstract",
        "read_document_overview",
        "read_document_detail",
    ]

    def __init__(self, config: SPSConfig | None = None):
        self.config = config or SPSConfig()
        self._transition_counts: dict[str, Counter[str]] = defaultdict(Counter)
        self._lock = threading.RLock()

    def learn(self, tool_sequence: list[str]) -> None:
        """从工具调用序列学习转移概率."""
        if not self.config.enabled or len(tool_sequence) < 2:
            return
        with self._lock:
            for i in range(len(tool_sequence) - 1):
                self._transition_counts[tool_sequence[i]][tool_sequence[i + 1]] += 1

    def predict_next(
        self, current_tool: str, top_k: int = 2
    ) -> list[tuple[str, float]]:
        """预测当前工具之后最可能的下一步工具。

        Returns:
            [(tool_name, confidence)] 降序排列，空列表表示无法预测。
        """
        if not self.config.enabled:
            return []

        with self._lock:
            if current_tool not in self._transition_counts:
                if current_tool == "search_knowledge_base":
                    return [(t, 0.7) for t in self.KB_SEARCH_NEXT[:top_k]]
                return []

            counter = self._transition_counts[current_tool]
            total = sum(counter.values())
            if total < 2:
                if current_tool == "search_knowledge_base":
                    return [(t, 0.6) for t in self.KB_SEARCH_NEXT[:top_k]]
                return []

            predictions = [
                (tool, count / total)
                for tool, count in counter.most_common(top_k)
            ]
            return [
                (t, s)
                for t, s in predictions
                if s >= self.config.speculation_threshold
            ]


class SpeculativeScheduler:
    """SPS 调度器：在 ReAct 循环中预测并预执行下一步工具。

    工作流程:
    1. Agent 执行工具 T1
    2. SPS 预测 T2
    3. 高置信度时预执行 T2，结果注入 context
    4. 预测错误时丢弃结果，降级为顺序执行
    """

    def __init__(self, config: SPSConfig | None = None):
        self.config = config or SPSConfig()
        self.predictor = ToolCallPredictor(config=self.config)
        self._lock = threading.RLock()

    def record_and_predict(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        tool_result: str,
    ) -> list[dict[str, Any]]:
        """记录工具执行结果并返回预判的下一工具调用。"""
        if not self.config.enabled:
            return []

        self.predictor.learn([tool_name])

        predictions = self.predictor.predict_next(tool_name, top_k=2)
        if not predictions:
            return []

        speculative_calls = []
        for next_tool, confidence in predictions:
            args = self._extract_next_args(tool_name, tool_args, tool_result, next_tool)
            if args is not None:
                speculative_calls.append(
                    {"name": next_tool, "args": args, "confidence": confidence}
                )
                logger.debug(
                    "SPS: predicted %s (conf=%.2f) after %s",
                    next_tool,
                    confidence,
                    tool_name,
                )

        return speculative_calls

    @staticmethod
    def _extract_next_args(
        current_tool: str,
        current_args: dict[str, Any],
        current_result: str,
        next_tool: str,
    ) -> dict[str, Any] | None:
        """从当前工具结果中提取下一工具调用的参数。"""
        if current_tool == "search_knowledge_base" and next_tool in (
            "read_document_abstract",
            "read_document_overview",
            "read_document_detail",
        ):
            doc_ids = _extract_doc_ids_from_result(current_result)
            if doc_ids:
                return {"doc_id": doc_ids[0]}
        return None

    def clear(self) -> None:
        with self._lock:
            pass


def _extract_doc_ids_from_result(result: str) -> list[str]:
    """从 search_knowledge_base 的结果字符串中提取 doc_id。

    结果格式: "1. [text]..." 其中文本来自 ChromaDB chunk metadata。
    我们从元数据中提取 doc_id（格式: {doc_id}_chunk_{i}）。
    """
    ids: list[str] = []
    for match in re.finditer(r"(\w+)_chunk_\d+", result):
        doc_id = match.group(1)
        if doc_id not in ids:
            ids.append(doc_id)
    return ids
