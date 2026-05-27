"""流式知识库搜索 — 增量返回结果以降低 TTFT."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from ...utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class StreamingSearchConfig:
    enabled: bool = True
    yield_first: int = 3


class StreamingKnowledgeBaseSearch:
    """流式知识库搜索封装。

    使用 KnowledgeBase.search_streaming() 增量返回结果，
    前 yield_first 条立即返回供 LLM 开始生成，剩余结果后续到达。

    目标: 降低 TTFT 20-30%。
    """

    def __init__(self, kb: Any, config: StreamingSearchConfig | None = None):
        self.kb = kb
        self.config = config or StreamingSearchConfig()

    def stream(
        self,
        query: str,
        top_k: int = 5,
        filter_dict: dict[str, Any] | None = None,
    ) -> Iterator[dict[str, Any]]:
        """流式搜索生成器。

        Yields:
            {"type": "first", "results": [...]}  — 前 yield_first 条
            {"type": "incremental", "results": [r]}  — 逐条后续
            {"type": "complete", "count": int}  — 全部完成
        """
        if not self.config.enabled:
            results = self.kb.search(query, top_k=top_k, filter_dict=filter_dict)
            yield {"type": "complete", "count": len(results), "results": results}
            return

        first_results: list[dict] = []
        remaining: list[dict] = []
        collected = 0

        try:
            for result in self.kb.search_streaming(
                query,
                top_k=top_k,
                filter_dict=filter_dict,
                yield_first=self.config.yield_first,
            ):
                if collected < self.config.yield_first:
                    first_results.append(result)
                else:
                    remaining.append(result)
                collected += 1

                if collected == self.config.yield_first:
                    yield {"type": "first", "results": first_results}

            for r in remaining:
                yield {"type": "incremental", "results": [r]}

            yield {"type": "complete", "count": collected}

        except Exception as e:
            logger.error("Streaming search failed: %s", e)
            yield {"type": "complete", "count": 0, "error": str(e)}
