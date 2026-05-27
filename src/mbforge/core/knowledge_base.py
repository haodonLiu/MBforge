"""知识库核心 - 基于 ChromaDB 的向量存储与检索.

设计参考：
- https://github.com/volcengine/OpenViking
- https://github.com/Tencent/TencentDB-Agent-Memory
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings

from .document import ExtractedContent
from .summarizer import SummaryManager
from ..utils.constants import KB_COLLECTION_DOCS, PROJECT_META_DIR
from ..utils.logger import get_logger

logger = get_logger(__name__)


class KnowledgeBase:
    """项目级知识库."""

    def __init__(self, project_root: Path, embedder=None):
        self.project_root = Path(project_root).resolve()
        self.meta_dir = self.project_root / PROJECT_META_DIR
        self.db_path = str(self.meta_dir / "chroma_db")
        self.embedder = embedder
        self._sm: SummaryManager | None = None

        self._client = chromadb.PersistentClient(
            path=self.db_path,
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=KB_COLLECTION_DOCS,
            metadata={"hnsw:space": "cosine"},
        )

    def _get_summary(self, doc_id: str):
        """Lazy-load SummaryManager and cache by doc_id."""
        if self._sm is None:
            self._sm = SummaryManager(self.project_root)
        return self._sm.load(doc_id)

    def close(self) -> None:
        """释放资源."""
        # ChromaDB PersistentClient 自动持久化
        # 重置客户端引用以释放文件句柄
        self._collection = None
        self._client = None

    def index_document(
        self,
        doc_id: str,
        content: ExtractedContent,
        metadata: dict[str, Any] | None = None,
        batch_size: int = 64,
    ) -> None:
        """将文档内容索引到知识库（分批处理避免 OOM）."""
        if not content.chunks:
            return

        base_meta = metadata or {}
        base_meta["doc_id"] = doc_id
        base_meta["source"] = content.metadata.get("source", "")

        total = len(content.chunks)
        for start in range(0, total, batch_size):
            end = min(start + batch_size, total)
            chunk_ids = []
            documents = []
            metadatas = []

            for i in range(start, end):
                chunk = content.chunks[i]
                chunk_id = f"{doc_id}_chunk_{i}"
                chunk_ids.append(chunk_id)
                documents.append(chunk)
                metadatas.append(
                    {
                        **base_meta,
                        "chunk_index": i,
                        "chunk_hash": hash(chunk) & 0xFFFFFFFF,
                    }
                )

            # 生成向量（按批）
            embeddings = None
            if self.embedder is not None:
                try:
                    embeddings = self.embedder.embed(documents)
                except Exception as e:
                    logger.warning(f"Embedding failed for batch {start}-{end}: {e}")

            add_kwargs = {
                "ids": chunk_ids,
                "documents": documents,
                "metadatas": metadatas,
            }
            if embeddings is not None:
                add_kwargs["embeddings"] = embeddings

            try:
                self._collection.add(**add_kwargs)
            except Exception as e:
                logger.error(f"KB add failed for batch {start}-{end}: {e}")

            logger.debug(
                "Indexed batch %d-%d/%d for %s", start, end, total, doc_id
            )

    def remove_document(self, doc_id: str) -> None:
        """移除文档的所有索引."""
        # ChromaDB 的 where 过滤
        self._collection.delete(where={"doc_id": doc_id})

    def search(
        self,
        query: str,
        top_k: int = 5,
        filter_dict: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """语义搜索."""
        if filter_dict is not None and not isinstance(filter_dict, dict):
            raise ValueError("filter_dict must be a dict")
        query_embedding = None
        if self.embedder is not None:
            try:
                query_embedding = self.embedder.embed([query])[0]
            except Exception as e:
                logger.warning(f"Query embedding failed: {e}")

        results = self._collection.query(
            query_embeddings=[query_embedding] if query_embedding else None,
            query_texts=[query] if query_embedding is None else None,
            n_results=top_k,
            where=filter_dict,
        )

        output = []
        ids = results.get("ids", [[]])[0]
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for i in range(len(ids)):
            output.append(
                {
                    "id": ids[i],
                    "text": docs[i],
                    "metadata": metas[i] if metas else {},
                    "distance": distances[i] if distances else 0.0,
                }
            )
        return output

    def hybrid_search(
        self,
        query: str,
        top_k: int = 5,
        reranker=None,
    ) -> list[dict[str, Any]]:
        """语义搜索 + Rerank."""
        candidates = self.search(query, top_k=top_k * 3)
        if reranker is None or len(candidates) <= top_k:
            return candidates[:top_k]

        passages = [c["text"] for c in candidates]
        ranked = reranker.rerank(query, passages)
        result = []
        for idx, score in ranked[:top_k]:
            item = candidates[idx]
            item["rerank_score"] = score
            result.append(item)
        return result

    def get_stats(self) -> dict[str, Any]:
        """获取知识库统计."""
        count = self._collection.count()
        return {
            "total_chunks": count,
            "db_path": self.db_path,
        }

    def search_by_directory(
        self,
        query: str,
        directory_prefix: str = "",
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """目录级语义搜索（OpenViking 递归目录检索）.

        先通过路径前缀过滤，再在子目录内做语义搜索。
        """
        results = self.search(query, top_k=top_k * 3)
        if directory_prefix:
            filtered = []
            for r in results:
                source = r.get("metadata", {}).get("source", "")
                if source.startswith(directory_prefix) or directory_prefix in source:
                    filtered.append(r)
            results = filtered
        return results[:top_k]

    def get_document_abstract(self, doc_id: str) -> str | None:
        """获取文档 L0 摘要."""
        summary = self._get_summary(doc_id)
        if summary:
            return summary.l0_abstract
        return None

    def get_document_overview(self, doc_id: str) -> str | None:
        """获取文档 L1 概览."""
        summary = self._get_summary(doc_id)
        if summary:
            return summary.l1_overview
        return None

    def get_document_keywords(self, doc_id: str) -> list[str]:
        """获取文档关键词."""
        summary = self._get_summary(doc_id)
        if summary:
            return summary.keywords
        return []

    def list_document_entities(self, doc_id: str) -> list[str]:
        """获取文档实体标签."""
        summary = self._get_summary(doc_id)
        if summary:
            return summary.entity_tags
        return []

    def search_streaming(
        self,
        query: str,
        top_k: int = 5,
        filter_dict: dict[str, Any] | None = None,
        yield_first: int = 3,
    ) -> Iterator[dict[str, Any]]:
        """增量流式搜索：先 yield 前 yield_first 条，再逐条 yield 剩余。"""
        if filter_dict is not None and not isinstance(filter_dict, dict):
            raise ValueError("filter_dict must be a dict")

        query_embedding = None
        if self.embedder is not None:
            try:
                query_embedding = self.embedder.embed([query])[0]
            except Exception as e:
                logger.warning("Query embedding failed: %s", e)

        results = self._collection.query(
            query_embeddings=[query_embedding] if query_embedding else None,
            query_texts=[query] if query_embedding is None else None,
            n_results=top_k,
            where=filter_dict,
        )

        ids = results.get("ids", [[]])[0]
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        first_batch_end = min(yield_first, len(ids))
        for i in range(first_batch_end):
            yield {
                "id": ids[i],
                "text": docs[i],
                "metadata": metas[i] if metas else {},
                "distance": distances[i] if distances else 0.0,
            }

        for i in range(first_batch_end, len(ids)):
            yield {
                "id": ids[i],
                "text": docs[i],
                "metadata": metas[i] if metas else {},
                "distance": distances[i] if distances else 0.0,
            }
