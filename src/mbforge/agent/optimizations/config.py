"""优化模块统一配置."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .semantic_cache import SemanticCacheConfig
from .stream_search import StreamingSearchConfig


@dataclass
class OptimizationConfig:
    """二层优化的统一配置（SPS 已移除，迁移到 Rust Agent）。"""

    semantic_cache: SemanticCacheConfig = field(default_factory=SemanticCacheConfig)
    streaming_search: StreamingSearchConfig = field(default_factory=StreamingSearchConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OptimizationConfig:
        sc_data = data.get("semantic_cache", {})
        ss_data = data.get("streaming_search", {})
        return cls(
            semantic_cache=SemanticCacheConfig(**sc_data) if sc_data else SemanticCacheConfig(),
            streaming_search=StreamingSearchConfig(**ss_data) if ss_data else StreamingSearchConfig(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "semantic_cache": {
                "enabled": self.semantic_cache.enabled,
                "max_size": self.semantic_cache.max_size,
                "ttl_seconds": self.semantic_cache.ttl_seconds,
                "similarity_threshold": self.semantic_cache.similarity_threshold,
                "disk_persist": self.semantic_cache.disk_persist,
                "hot_query_threshold": self.semantic_cache.hot_query_threshold,
            },
            "streaming_search": {
                "enabled": self.streaming_search.enabled,
                "yield_first": self.streaming_search.yield_first,
            },
        }
