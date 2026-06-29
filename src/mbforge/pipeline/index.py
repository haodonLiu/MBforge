"""Index stage — embed chunks and store in Zvec vector database.

Takes chunked text, generates embeddings via Qwen3, and indexes into Zvec.
"""

from __future__ import annotations

import json
from typing import Any

from ..utils.logger import get_logger

logger = get_logger("mbforge.pipeline.index")


def index_chunks(
    doc_id: str,
    chunks: list[dict],
    collection_path: str,
    embed_dim: int = 1024,
) -> dict[str, Any]:
    """Embed and index text chunks into Zvec.

    Args:
        doc_id: Document identifier
        chunks: List of {'chunk_id', 'text', 'metadata'} dicts
        collection_path: Path to Zvec collection directory
        embed_dim: Embedding dimension

    Returns:
        {'indexed': int, 'doc_id': str}
    """
    if not chunks:
        return {"indexed": 0, "doc_id": doc_id}

    from ..backends import qwen3_embed, zvec

    # Ensure collection is open
    zvec.open_collection(collection_path, embed_dim)

    # Extract texts for embedding
    texts = [c["text"] for c in chunks]
    chunk_ids = [c["chunk_id"] for c in chunks]
    metadatas = [json.dumps(c["metadata"], ensure_ascii=False) for c in chunks]

    # Embed in batches
    batch_size = 32
    all_embeddings: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        try:
            embeddings = qwen3_embed.embed(batch)
            all_embeddings.extend(embeddings)
        except Exception as e:
            logger.error("Embedding failed for batch %d: %s", i // batch_size, e)
            # Fallback: zero vectors
            all_embeddings.extend([[0.0] * embed_dim] * len(batch))

    # Index into Zvec
    result = zvec.index_document(doc_id, chunk_ids, texts, metadatas, all_embeddings)
    logger.info("Indexed %d chunks for doc %s", result.get("indexed", 0), doc_id)
    return {"indexed": result.get("indexed", len(chunks)), "doc_id": doc_id}


def delete_doc_index(doc_id: str, collection_path: str) -> bool:
    """Remove all chunks for a document from the index."""
    try:
        from ..backends import zvec

        zvec.delete_document(doc_id)
        return True
    except Exception as e:
        logger.warning("Failed to delete index for %s: %s", doc_id, e)
        return False
