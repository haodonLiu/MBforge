"""知识库核心 - 基于 ChromaDB 的向量存储与检索.

设计参考：
- https://github.com/volcengine/OpenViking
- https://github.com/Tencent/TencentDB-Agent-Memory
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import chromadb
from chromadb.config import Settings

from .document import DocumentProcessor, ExtractedContent
from ..utils.constants import KB_COLLECTION_DOCS, PROJECT_META_DIR
from ..utils.helpers import generate_uuid


class KnowledgeBase:
    """项目级知识库."""

    def __init__(self, project_root: Path, embedder=None):
        self.project_root = Path(project_root).resolve()
        self.meta_dir = self.project_root / PROJECT_META_DIR
        self.db_path = str(self.meta_dir / "chroma_db")
        self.embedder = embedder

        self._client = chromadb.PersistentClient(
            path=self.db_path,
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=KB_COLLECTION_DOCS,
            metadata={"hnsw:space": "cosine"},
        )

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
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """将文档内容索引到知识库."""
        if not content.chunks:
            return

        chunk_ids = []
        documents = []
        metadatas = []

        base_meta = metadata or {}
        base_meta["doc_id"] = doc_id
        base_meta["source"] = content.metadata.get("source", "")

        for i, chunk in enumerate(content.chunks):
            chunk_id = f"{doc_id}_chunk_{i}"
            chunk_ids.append(chunk_id)
            documents.append(chunk)
            meta = {
                **base_meta,
                "chunk_index": i,
                "chunk_hash": hash(chunk) & 0xFFFFFFFF,
            }
            metadatas.append(meta)

        # 生成向量
        embeddings = None
        if self.embedder is not None:
            try:
                embeddings = self.embedder.embed(documents)
            except Exception as e:
                print(f"Embedding failed: {e}")

        self._collection.add(
            ids=chunk_ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=embeddings,
        )

    def remove_document(self, doc_id: str) -> None:
        """移除文档的所有索引."""
        # ChromaDB 的 where 过滤
        self._collection.delete(where={"doc_id": doc_id})

    def search(
        self,
        query: str,
        top_k: int = 5,
        filter_dict: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """语义搜索."""
        query_embedding = None
        if self.embedder is not None:
            try:
                query_embedding = self.embedder.embed([query])[0]
            except Exception as e:
                print(f"Query embedding failed: {e}")

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
            output.append({
                "id": ids[i],
                "text": docs[i],
                "metadata": metas[i] if metas else {},
                "distance": distances[i] if distances else 0.0,
            })
        return output

    def hybrid_search(
        self,
        query: str,
        top_k: int = 5,
        reranker=None,
    ) -> List[Dict[str, Any]]:
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

    def get_stats(self) -> Dict[str, Any]:
        """获取知识库统计."""
        count = self._collection.count()
        return {
            "total_chunks": count,
            "db_path": self.db_path,
        }
