"""Zvec vector search backend.

Manages a local Zvec collection for dense vector + full-text + hybrid search.
The collection is opened lazily per path; all write operations are serialized
with a process-level lock because Zvec collections require single-writer access.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from ..utils.helpers import ValidationError
from ..utils.logger import get_logger

logger = get_logger(__name__)

_COLLECTION: Any | None = None
_COLLECTION_PATH: str | None = None
_COLLECTION_DIM: int = 0
_AVAILABLE: bool = False
_ERROR: str = ""
_INITIALIZED: bool = False
_WRITE_LOCK = threading.Lock()


def _ensure_initialized() -> None:
    """Initialize the Zvec C++ runtime once per process."""
    global _INITIALIZED
    if _INITIALIZED:
        return
    try:
        import zvec

        zvec.init(log_level=zvec.LogLevel.WARN)
        _INITIALIZED = True
        logger.debug("Zvec runtime initialized")
    except Exception as exc:
        logger.error("Zvec initialization failed: %s", exc)
        raise


def load(path: str | None = None, dim: int | None = None) -> None:
    """Verify that the Zvec Python SDK is importable and can be initialized."""
    global _AVAILABLE, _ERROR
    if _AVAILABLE:
        return
    try:
        _ensure_initialized()
        _AVAILABLE = True
        _ERROR = ""
        logger.info("Zvec backend ready")
    except Exception as exc:
        _ERROR = str(exc)
        _AVAILABLE = False
        logger.error("Zvec backend load failed: %s", exc)


def unload() -> None:
    """Release the collection handle."""
    global _COLLECTION, _COLLECTION_PATH, _COLLECTION_DIM, _AVAILABLE, _ERROR
    with _WRITE_LOCK:
        _COLLECTION = None
        _COLLECTION_PATH = None
        _COLLECTION_DIM = 0
    _AVAILABLE = False
    _ERROR = ""
    logger.info("Zvec backend unloaded")


def health() -> dict[str, str]:
    return {
        "status": "ready" if _AVAILABLE else ("error" if _ERROR else "loading"),
        "error": _ERROR,
    }


def _collection_module() -> Any:
    """Return the imported zvec module (runtime is already initialized)."""
    import zvec

    return zvec


def _open_collection(path: str, dim: int) -> Any:
    """Open or create a collection at ``path`` with the MBForge KB schema."""
    global _COLLECTION, _COLLECTION_PATH, _COLLECTION_DIM

    if _COLLECTION is not None and path == _COLLECTION_PATH and dim == _COLLECTION_DIM:
        return _COLLECTION

    zvec = _collection_module()
    Path(path).parent.mkdir(parents=True, exist_ok=True)

    schema = zvec.CollectionSchema(
        name="mbforge_kb",
        fields=[
            zvec.FieldSchema(
                "chunk_id",
                zvec.DataType.STRING,
                nullable=False,
                index_param=zvec.InvertIndexParam(),
            ),
            zvec.FieldSchema(
                "doc_id",
                zvec.DataType.STRING,
                nullable=False,
                index_param=zvec.InvertIndexParam(),
            ),
            zvec.FieldSchema(
                "text",
                zvec.DataType.STRING,
                nullable=False,
                index_param=zvec.FtsIndexParam(tokenizer_name="standard"),
            ),
            zvec.FieldSchema("metadata", zvec.DataType.STRING, nullable=False),
        ],
        vectors=[
            zvec.VectorSchema(
                "embedding",
                zvec.DataType.VECTOR_FP32,
                dimension=dim,
                index_param=zvec.HnswIndexParam(
                    metric_type=zvec.MetricType.COSINE,
                    m=16,
                    ef_construction=200,
                ),
            )
        ],
    )

    collection = zvec.create_and_open(path, schema)
    _COLLECTION = collection
    _COLLECTION_PATH = path
    _COLLECTION_DIM = dim
    logger.info("Zvec collection opened: %s (dim=%d)", path, dim)
    return collection


def open_collection(path: str, dim: int) -> dict[str, Any]:
    """Public open handler called by the FastAPI endpoint."""
    if not path or dim <= 0:
        raise ValidationError("path and positive dim are required")
    with _WRITE_LOCK:
        load()
        _open_collection(path, dim)
    return {"success": True}


def _validate_index_payload(
    doc_id: str,
    chunk_ids: list[str],
    texts: list[str],
    metadatas: list[str],
    embeddings: list[list[float]],
) -> None:
    """Validate parallel-array shape and content."""
    if not doc_id:
        raise ValidationError("doc_id is required")
    n = len(chunk_ids)
    if n == 0:
        raise ValidationError("chunk_ids must not be empty")
    if not (len(texts) == len(metadatas) == len(embeddings) == n):
        raise ValidationError(
            "chunk_ids, texts, metadatas and embeddings must have the same length"
        )
    for cid in chunk_ids:
        if not cid:
            raise ValidationError("chunk_id must not be empty")


def index_document(
    doc_id: str,
    chunk_ids: list[str],
    texts: list[str],
    metadatas: list[str],
    embeddings: list[list[float]],
) -> dict[str, Any]:
    """Replace all chunks for ``doc_id`` in the collection."""
    if _COLLECTION is None:
        raise ValidationError("collection not opened")
    _validate_index_payload(doc_id, chunk_ids, texts, metadatas, embeddings)

    zvec = _collection_module()
    dim = _COLLECTION_DIM

    docs: list[Any] = []
    for i, cid in enumerate(chunk_ids):
        vector = embeddings[i]
        if len(vector) != dim:
            raise ValidationError(
                f"embedding dimension mismatch at index {i}: expected {dim}, got {len(vector)}"
            )
        docs.append(
            zvec.Doc(
                id=cid,
                fields={
                    "chunk_id": cid,
                    "doc_id": doc_id,
                    "text": texts[i],
                    "metadata": metadatas[i],
                },
                vectors={"embedding": vector},
            )
        )

    with _WRITE_LOCK:
        _COLLECTION.delete_by_filter(f"doc_id = '{doc_id}'")
        statuses = _COLLECTION.upsert(docs)

    failed = [
        i
        for i, status in enumerate(statuses)
        if not getattr(status, "ok", lambda: True)()
    ]
    if failed:
        errors = [str(statuses[i]) for i in failed]
        raise RuntimeError(
            f"Zvec insert failed for chunks {failed}: {'; '.join(errors)}"
        )

    logger.debug("Indexed %d chunks for doc %s", len(docs), doc_id)
    return {"indexed": len(docs)}


def delete_document(doc_id: str) -> dict[str, Any]:
    """Delete all chunks belonging to ``doc_id``."""
    if _COLLECTION is None:
        raise ValidationError("collection not opened")
    if not doc_id:
        raise ValidationError("doc_id is required")

    with _WRITE_LOCK:
        status = _COLLECTION.delete_by_filter(f"doc_id = '{doc_id}'")

    logger.debug("Deleted chunks for doc %s: %s", doc_id, status)
    return {"deleted": True}


def _format_results(results: Any) -> list[dict[str, Any]]:
    """Convert a Zvec DocList to the Rust SearchResult shape."""
    out: list[dict[str, Any]] = []
    for doc in results:
        fields = dict(doc.fields) if doc.fields else {}
        metadata: dict[str, Any] = {}
        try:
            metadata = json.loads(fields.get("metadata", "{}"))
        except json.JSONDecodeError:
            metadata = {"_raw": fields.get("metadata", "")}
        out.append(
            {
                "id": doc.id,
                "text": fields.get("text", ""),
                "metadata": metadata,
                "score": doc.score if doc.score is not None else 0.0,
            }
        )
    return out


def vector_search(
    query_embedding: list[float],
    top_k: int,
    doc_id_filter: str | None = None,
) -> dict[str, Any]:
    """Dense vector search."""
    if _COLLECTION is None:
        raise ValidationError("collection not opened")
    if not query_embedding or top_k <= 0:
        raise ValidationError("query_embedding and positive top_k are required")

    zvec = _collection_module()
    query = zvec.Query(
        field_name="embedding",
        vector=query_embedding,
        param=zvec.HnswQueryParam(ef=max(100, top_k * 2)),
    )
    flt = f"doc_id = '{doc_id_filter}'" if doc_id_filter else None
    results = _COLLECTION.query(
        queries=query,
        topk=top_k,
        filter=flt,
        output_fields=["chunk_id", "doc_id", "text", "metadata"],
    )
    return {"results": _format_results(results)}


def text_search(
    query: str,
    top_k: int,
    doc_id_filter: str | None = None,
) -> dict[str, Any]:
    """Full-text search over the ``text`` field."""
    if _COLLECTION is None:
        raise ValidationError("collection not opened")
    if not query or top_k <= 0:
        raise ValidationError("query and positive top_k are required")

    zvec = _collection_module()
    q = zvec.Query(
        field_name="text",
        fts=zvec.Fts(query_string=query),
        param=zvec.FtsQueryParam(),
    )
    flt = f"doc_id = '{doc_id_filter}'" if doc_id_filter else None
    results = _COLLECTION.query(
        queries=q,
        topk=top_k,
        filter=flt,
        output_fields=["chunk_id", "doc_id", "text", "metadata"],
    )
    return {"results": _format_results(results)}


def hybrid_search(
    query_vec: list[float],
    query_text: str,
    top_k: int,
    doc_id_filter: str | None = None,
) -> dict[str, Any]:
    """Vector + FTS fusion via RRF."""
    if _COLLECTION is None:
        raise ValidationError("collection not opened")
    if not query_vec or not query_text or top_k <= 0:
        raise ValidationError("query_vec, query_text and positive top_k are required")

    zvec = _collection_module()
    vq = zvec.Query(
        field_name="embedding",
        vector=query_vec,
        param=zvec.HnswQueryParam(ef=max(100, top_k * 6)),
    )
    tq = zvec.Query(
        field_name="text",
        fts=zvec.Fts(query_string=query_text),
        param=zvec.FtsQueryParam(),
    )
    flt = f"doc_id = '{doc_id_filter}'" if doc_id_filter else None
    results = _COLLECTION.query(
        queries=[vq, tq],
        topk=top_k * 3,
        filter=flt,
        output_fields=["chunk_id", "doc_id", "text", "metadata"],
        reranker=zvec.RrfReRanker(rank_constant=60),
    )
    return {"results": _format_results(results)}


def count() -> dict[str, Any]:
    """Return total number of indexed chunks."""
    if _COLLECTION is None:
        raise ValidationError("collection not opened")
    return {"count": _COLLECTION.stats.doc_count}
