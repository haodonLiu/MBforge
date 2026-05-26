"""Reranker 推理路由."""

from fastapi import APIRouter, Request

from ..models.reranker import get_reranker
from .health import set_model_status

router = APIRouter()


@router.post("/rerank")
async def rerank(request: Request) -> dict:
    try:
        body = await request.json()
        query = body.get("query", "")
        passages = body.get("passages", [])
        top_n = body.get("top_n", 5)

        reranker = get_reranker()
        results = reranker.rerank(query, passages)
        top_results = sorted(results, key=lambda x: x[1], reverse=True)[:top_n]
        set_model_status("reranker", "ready")
        return {"results": [{"index": idx, "score": score} for idx, score in top_results]}
    except Exception as e:
        set_model_status("reranker", "error")
        return {"results": [], "error": str(e)}
