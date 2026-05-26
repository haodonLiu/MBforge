"""Embedder 推理路由."""

from fastapi import APIRouter, Request

from ..models.embedder import get_embedder
from .health import set_model_status

router = APIRouter()


@router.post("/embed")
async def embed(request: Request) -> dict:
    try:
        body = await request.json()
        texts = body.get("texts", [])
        if isinstance(texts, str):
            texts = [texts]

        embedder = get_embedder()
        embeddings = embedder.embed(texts)
        set_model_status("embedder", "ready")
        return {"embeddings": embeddings}
    except Exception as e:
        set_model_status("embedder", "error")
        return {"embeddings": [], "error": str(e)}
