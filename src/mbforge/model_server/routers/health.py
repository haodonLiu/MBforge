"""健康检查路由."""

from fastapi import APIRouter

from ...utils.logger import get_logger
from ..models.llm import get_llm
from ..models.embedder import get_embedder
from ..models.reranker import get_reranker
from ..models.vlm import get_vlm
from ..models.moldet import get_moldet

logger = get_logger(__name__)
router = APIRouter()

_model_status = {
    "llm": "loading",
    "embedder": "loading",
    "reranker": "loading",
    "vlm": "loading",
    "uniparser": "loading",
    "moldet": "loading",
}


@router.get("/health")
async def health_check() -> dict:
    # 尝试初始化各模型（触发懒加载）
    try:
        get_llm()
        _model_status["llm"] = "ready"
    except Exception as e:
        _model_status["llm"] = "error"
        logger.debug(f"LLM health check failed: {e}")

    try:
        get_embedder()
        _model_status["embedder"] = "ready"
    except Exception as e:
        _model_status["embedder"] = "error"
        logger.debug(f"Embedder health check failed: {e}")

    try:
        get_reranker()
        _model_status["reranker"] = "ready"
    except Exception as e:
        _model_status["reranker"] = "error"
        logger.debug(f"Reranker health check failed: {e}")

    try:
        get_vlm()
        _model_status["vlm"] = "ready"
    except Exception as e:
        _model_status["vlm"] = "error"
        logger.debug(f"VLM health check failed: {e}")

    # UniParser 健康检查（通过环境变量配置）
    try:
        import os
        from mbforge.parsers.uniparser.uniparser_config import ParserConfig
        from mbforge.parsers.uniparser.uniparser_client import ParserClient

        host = os.environ.get("UNIPARSER_HOST", "")
        api_key = os.environ.get("UNIPARSER_API_KEY", "")
        if host and api_key:
            client = ParserClient(ParserConfig(host=host, api_key=api_key))
            client.health()
            _model_status["uniparser"] = "ready"
        else:
            _model_status["uniparser"] = "error"
            logger.debug("UniParser not configured (missing env vars)")
    except Exception as e:
        _model_status["uniparser"] = "error"
        logger.debug(f"UniParser health check failed: {e}")

    # MolDet 健康检查
    try:
        pipeline = get_moldet()
        if pipeline and pipeline.is_available():
            _model_status["moldet"] = "ready"
        else:
            _model_status["moldet"] = "error"
    except Exception as e:
        _model_status["moldet"] = "error"
        logger.debug(f"MolDet health check failed: {e}")

    statuses = list(_model_status.values())
    if all(s == "ready" for s in statuses):
        overall = "online"
    elif any(s == "ready" for s in statuses):
        overall = "partial"
    elif any(s == "error" for s in statuses):
        overall = "error"
    else:
        overall = "loading"

    return {
        "status": overall,
        "models": dict(_model_status),
        "error": None,
    }


def set_model_status(name: str, status: str) -> None:
    _model_status[name] = status
