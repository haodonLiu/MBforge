"""健康检查路由."""

from fastapi import APIRouter

router = APIRouter()

_model_status = {
    "llm": "loading",
    "embedder": "loading",
    "reranker": "loading",
    "vlm": "loading",
}


@router.get("/health")
async def health_check() -> dict:
    return {
        "status": "loading",
        "models": _model_status,
        "error": None,
    }


def set_model_status(name: str, status: str) -> None:
    _model_status[name] = status
