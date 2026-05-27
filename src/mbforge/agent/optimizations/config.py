"""优化模块统一配置."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .semantic_cache import SemanticCacheConfig
from .sps_scheduler import SPSConfig
from .stream_search import StreamingSearchConfig


@dataclass
class OptimizationConfig:
    """三层优化的统一配置."""

    semantic_cache: SemanticCacheConfig = field(default_factory=SemanticCacheConfig)
    sps: SPSConfig = field(default_factory=SPSConfig)
    streaming_search: StreamingSearchConfig = field(default_factory=StreamingSearchConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OptimizationConfig:
        sc_data = data.get("semantic_cache", {})
        sps_data = data.get("sps", {})
        ss_data = data.get("streaming_search", {})
        return cls(
            semantic_cache=SemanticCacheConfig(**sc_data) if sc_data else SemanticCacheConfig(),
            sps=SPSConfig(**sps_data) if sps_data else SPSConfig(),
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
            "sps": {
                "enabled": self.sps.enabled,
                "speculation_threshold": self.sps.speculation_threshold,
            },
            "streaming_search": {
                "enabled": self.streaming_search.enabled,
                "yield_first": self.streaming_search.yield_first,
            },
        }
