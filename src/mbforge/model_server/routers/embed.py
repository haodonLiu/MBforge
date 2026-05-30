"""Embedder 推理路由."""

import asyncio

from fastapi import APIRouter, Request

from ...utils.exceptions import ModelNotAvailableError
from ...utils.logger import get_logger
from ..models.embedder import get_embedder
from .health import set_model_status

logger = get_logger(__name__)
router = APIRouter()


@router.post("/embed")
async def embed(request: Request) -> dict:
    try:
        body = await request.json()
        texts = body.get("texts", [])
        if isinstance(texts, str):
            texts = [texts]

        embedder = get_embedder()
        loop = asyncio.get_running_loop()
        embeddings = await loop.run_in_executor(None, lambda: embedder.embed(texts))
        set_model_status("embedder", "ready")
        return {"embeddings": embeddings}
    except Exception as e:
        set_model_status("embedder", "error")
        logger.error(f"Embedding failed: {e}", exc_info=True)
        raise ModelNotAvailableError(str(e))
