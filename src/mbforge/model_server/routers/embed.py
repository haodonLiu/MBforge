"""Embedder 推理路由."""
from typing import Any

from fastapi import APIRouter, Request

from ...utils.exceptions import ModelNotAvailableError
from ...utils.logger import get_logger
from mbforge.models.base import run_sync_async
from ..models.embedder import get_embedder
from .health import set_model_status

logger = get_logger(__name__)
router = APIRouter()


@router.post("/embed")
async def embed(request: Request) -> dict[str, Any]:
    """Compute text embeddings.

    Called by Rust:
      - src-tauri/src/core/vector/embedding.rs::embed_with_trace
    """
    # 读取跨语言 trace 上下文
    trace_id = request.headers.get("X-Trace-Id")
    span_id = request.headers.get("X-Span-Id")
    if trace_id:
        logger.info(f"[trace={trace_id} span={span_id}] embed started")
    try:
        body = await request.json()
        texts = body.get("texts", [])
        if isinstance(texts, str):
            texts = [texts]

        if trace_id:
            logger.info(f"[trace={trace_id} span={span_id}] embedding {len(texts)} texts")
        embedder = get_embedder()
        embeddings = await run_sync_async(embedder.embed, texts)
        set_model_status("embedder", "ready")
        if trace_id:
            logger.info(f"[trace={trace_id} span={span_id}] embed done, dim={len(embeddings[0]) if embeddings else 0}")
        return {"embeddings": embeddings}
    except Exception as e:
        set_model_status("embedder", "error")
        log_extra = f" trace={trace_id}" if trace_id else ""
        logger.error(f"Embedding failed{log_extra}: {e}", exc_info=True)
        raise ModelNotAvailableError(str(e))