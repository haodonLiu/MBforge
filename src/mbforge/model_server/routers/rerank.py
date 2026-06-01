"""Reranker 推理路由."""
from typing import Any

import asyncio

from fastapi import APIRouter, Request

from ...utils.exceptions import ModelNotAvailableError
from ...utils.logger import get_logger
from ..models.reranker import get_reranker
from .health import set_model_status

logger = get_logger(__name__)
router = APIRouter()


@router.post("/rerank")
async def rerank(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
        query = body.get("query", "")
        passages = body.get("passages", [])
        top_n = body.get("top_n", 5)

        reranker = get_reranker()
        loop = asyncio.get_running_loop()
        results = await loop.run_in_executor(None, lambda: reranker.rerank(query, passages))
        top_results = sorted(results, key=lambda x: x[1], reverse=True)[:top_n]
        set_model_status("reranker", "ready")
        return {"results": [{"index": idx, "score": score} for idx, score in top_results]}
    except Exception as e:
        set_model_status("reranker", "error")
        logger.error(f"Rerank failed: {e}", exc_info=True)
        raise ModelNotAvailableError(str(e))
