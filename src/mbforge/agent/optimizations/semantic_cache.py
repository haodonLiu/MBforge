"""三层语义缓存 (L1 exact / L2 embedding / L3 hot-query)."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ...utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class CacheEntry:
    """缓存条目：存储搜索结果，不缓存 LLM 最终回答."""

    query_hash: str
    query_text: str
    embedding: list[float] | None
    results: list[dict]
    project_root: str
    created_at: float = field(default_factory=time.time)
    hit_count: int = 1
    last_hit: float = field(default_factory=time.time)

    def is_expired(self, ttl: float) -> bool:
        return (time.time() - self.created_at) > ttl

    def update_hit(self) -> None:
        self.hit_count += 1
        self.last_hit = time.time()


@dataclass
class SemanticCacheConfig:
    """缓存配置."""

    enabled: bool = True
    max_size: int = 1000
    ttl_seconds: float = 3600.0
    similarity_threshold: float = 0.95
    disk_persist: bool = True
    hot_query_threshold: int = 3


class SemanticCache:
    """三层缓存策略：L1 精确匹配 / L2 语义近似 / L3 高频预热。

    仅缓存 KB 搜索结果（doc_ids + text + metadata + distance），
    不缓存 LLM 最终回答。
    """

    def __init__(
        self,
        project_root: Path,
        embedder: Any,
        config: SemanticCacheConfig | None = None,
    ):
        self.project_root = Path(project_root).resolve()
        self.embedder = embedder
        self.config = config or SemanticCacheConfig()

        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.RLock()
        self._hot_queries: list[str] = []

        if self.config.disk_persist:
            self._cache_path = (
                self.project_root / ".mbforge" / "cache" / "semantic_cache.json"
            )
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            self._load_from_disk()

    # ---- L1: Exact hash match ----

    def _hash_query(self, query: str) -> str:
        return hashlib.sha256(query.encode("utf-8")).hexdigest()[:32]

    def get_l1(self, query: str) -> list[dict] | None:
        """O(1) 精确匹配."""
        if not self.config.enabled:
            return None
        key = self._hash_query(query)
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            if entry.is_expired(self.config.ttl_seconds):
                del self._cache[key]
                return None
            entry.update_hit()
            self._cache.move_to_end(key)
            logger.debug("L1 cache hit: %s", query[:50])
            return entry.results

    # ---- L2: Embedding similarity ----

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        """余弦相似度。向量已 L2-normalized，点积即余弦。"""
        return sum(x * y for x, y in zip(a, b))

    def get_l2(self, query: str) -> list[dict] | None:
        """语义近似匹配：embedding 余弦 > threshold."""
        if not self.config.enabled or self.embedder is None:
            return None
        try:
            query_emb = self.embedder.embed([query])[0]
        except Exception:
            return None

        best_entry: CacheEntry | None = None
        best_sim = 0.0

        with self._lock:
            for entry in self._cache.values():
                if entry.embedding is None or entry.is_expired(self.config.ttl_seconds):
                    continue
                sim = self._cosine(query_emb, entry.embedding)
                if sim > best_sim:
                    best_sim = sim
                    best_entry = entry

        if best_entry is not None and best_sim >= self.config.similarity_threshold:
            best_entry.update_hit()
            logger.debug("L2 cache hit: sim=%.4f, query=%s", best_sim, query[:50])
            return best_entry.results
        return None

    # ---- L3: Hot query prefetch ----

    def prefetch_hot_queries(self) -> None:
        """预热高频查询：hit_count >= threshold 的条目标记为热点。"""
        with self._lock:
            self._hot_queries = [
                k
                for k, e in self._cache.items()
                if e.hit_count >= self.config.hot_query_threshold
            ]
        logger.info("L3 hot queries loaded: %d", len(self._hot_queries))

    # ---- Store ----

    def store(self, query: str, results: list[dict]) -> None:
        """缓存 KB 搜索结果。"""
        if not self.config.enabled or not results:
            return
        key = self._hash_query(query)
        embedding = None
        if self.config.similarity_threshold > 0 and self.embedder is not None:
            try:
                embedding = self.embedder.embed([query])[0]
            except Exception:
                pass

        entry = CacheEntry(
            query_hash=key,
            query_text=query,
            embedding=embedding,
            results=results,
            project_root=str(self.project_root),
        )

        with self._lock:
            if len(self._cache) >= self.config.max_size and key not in self._cache:
                evicted_key = next(iter(self._cache))
                del self._cache[evicted_key]
                logger.debug("Cache evicted: %s", evicted_key)
            self._cache[key] = entry
            self._cache.move_to_end(key)

        if self.config.disk_persist:
            self._save_to_disk()

    # ---- Persistence ----

    def _load_from_disk(self) -> None:
        if not self._cache_path.exists():
            return
        try:
            with open(self._cache_path, encoding="utf-8") as f:
                data = json.load(f)
            entries = {}
            for key, item in data.items():
                entries[key] = CacheEntry(
                    query_hash=item["query_hash"],
                    query_text=item["query_text"],
                    embedding=item.get("embedding"),
                    results=item["results"],
                    project_root=item["project_root"],
                    created_at=item.get("created_at", time.time()),
                    hit_count=item.get("hit_count", 1),
                    last_hit=item.get("last_hit", time.time()),
                )
            self._cache = OrderedDict(entries)
            self.prefetch_hot_queries()
            logger.info("Semantic cache loaded: %d entries", len(self._cache))
        except Exception as e:
            logger.warning("Failed to load semantic cache: %s", e)

    def _save_to_disk(self) -> None:
        try:
            data = {
                k: {
                    "query_hash": v.query_hash,
                    "query_text": v.query_text,
                    "embedding": v.embedding,
                    "results": v.results,
                    "project_root": v.project_root,
                    "created_at": v.created_at,
                    "hit_count": v.hit_count,
                    "last_hit": v.last_hit,
                }
                for k, v in self._cache.items()
            }
            with open(self._cache_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning("Failed to save semantic cache: %s", e)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            self._hot_queries.clear()
        if hasattr(self, "_cache_path") and self._cache_path.exists():
            self._cache_path.unlink()

    def stats(self) -> dict[str, Any]:
        with self._lock:
            total_hits = sum(e.hit_count for e in self._cache.values())
            return {
                "entries": len(self._cache),
                "total_hits": total_hits,
                "hot_queries": len(self._hot_queries),
                "max_size": self.config.max_size,
                "ttl_seconds": self.config.ttl_seconds,
                "similarity_threshold": self.config.similarity_threshold,
            }
