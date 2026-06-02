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
    try:
        body = await request.json()
        texts = body.get("texts", [])
        if isinstance(texts, str):
            texts = [texts]

        embedder = get_embedder()
        embeddings = await run_sync_async(embedder.embed, texts)
        set_model_status("embedder", "ready")
        return {"embeddings": embeddings}
    except Exception as e:
        set_model_status("embedder", "error")
        logger.error(f"Embedding failed: {e}", exc_info=True)
        raise ModelNotAvailableError(str(e))
