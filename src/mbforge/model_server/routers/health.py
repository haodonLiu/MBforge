"""健康检查路由 — 集成 ResourceManager 资源状态."""

import time

from fastapi import APIRouter

from ...core.resource_manager import ResourceManager, ResourceStatus
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

# 资源状态缓存（避免每次 health 请求都做递归文件系统扫描）
_resource_cache: dict[str, str] = {}
_resource_cache_time: float = 0.0
_RESOURCE_CACHE_TTL = 60.0  # 60 秒刷新一次


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
        import requests

        host = os.environ.get("UNIPARSER_HOST", "")
        api_key = os.environ.get("UNIPARSER_API_KEY", "")
        if host and api_key:
            resp = requests.get(
                f"{host.rstrip('/')}/health",
                headers={"X-API-Key": api_key},
                timeout=10,
            )
            if resp.ok:
                _model_status["uniparser"] = "ready"
            else:
                _model_status["uniparser"] = "error"
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

    # 计算整体状态
    statuses = list(_model_status.values())
    if all(s == "ready" for s in statuses):
        overall = "online"
    elif any(s == "ready" for s in statuses):
        overall = "partial"
    elif any(s == "error" for s in statuses):
        overall = "error"
    else:
        overall = "loading"

    # 资源下载状态（带缓存，避免每次请求都做递归文件系统扫描）
    global _resource_cache, _resource_cache_time
    now = time.monotonic()
    if now - _resource_cache_time > _RESOURCE_CACHE_TTL:
        try:
            _resource_cache = {}
            for rid in ResourceManager.catalog:
                res = ResourceManager.check(rid)
                _resource_cache[rid] = res.status.value
            _resource_cache_time = now
        except Exception as e:
            logger.debug(f"Resource status check failed: {e}")
    resource_status = dict(_resource_cache)

    return {
        "status": overall,
        "models": dict(_model_status),
        "resources": resource_status,
        "error": None,
    }


def set_model_status(name: str, status: str) -> None:
    _model_status[name] = status
