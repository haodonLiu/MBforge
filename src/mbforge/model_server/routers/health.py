"""Health check route — aggregates ResourceManager resource status + loaded
embed / rerank / VLM / moldet model health.

The LLM is no longer hosted by this sidecar (it's called directly from
Rust via `core::agent::rig_adapter` against the user-supplied
`MBFORGE_LLM_*` endpoint), so it is **not** part of this health check.
"""
from typing import Any

import time

from fastapi import APIRouter

from ...core.resource_manager import ResourceManager
from ...utils.logger import get_logger
from ..models.embedder import get_embedder
from ..models.reranker import get_reranker
from ..models.vlm import get_vlm
from ..models.moldet import get_moldet

logger = get_logger(__name__)
router = APIRouter()

_model_status = {
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

# Phase 3 熔断器：每个模型失败后冷却时间内不重试。
# 解决"每 5 秒 health poll 反复触发昂贵的 model init"问题。
_RETRY_COOLDOWN = 30.0  # 失败后 30 秒内不再尝试
_last_failure: dict[str, float] = {}


def _should_skip_due_to_cooldown(model_name: str) -> bool:
    """检查是否在熔断冷却期内。返回 True 表示跳过调用、直接返回上次的失败状态。"""
    last = _last_failure.get(model_name)
    if last is None:
        return False
    return (time.monotonic() - last) < _RETRY_COOLDOWN


def _mark_failure(model_name: str) -> None:
    _last_failure[model_name] = time.monotonic()


def _clear_failure(model_name: str) -> None:
    _last_failure.pop(model_name, None)


@router.get("/health")
async def health_check() -> dict[str, Any]:
    """Aggregate health check across loaded models + resources.

    Called by Rust:
      - src-tauri/src/sidecar.rs::start_health_monitor

    Phase 3 改造：每个模型 init 失败后进入 30s 熔断冷却，
    避免 Rust 5s health poll 反复触发昂贵初始化。
    """
    # Embedder
    if _should_skip_due_to_cooldown("embedder"):
        # 在冷却期内：保持上次状态
        pass
    else:
        try:
            get_embedder()
            _model_status["embedder"] = "ready"
            _clear_failure("embedder")
        except Exception as e:
            _model_status["embedder"] = "error"
            _mark_failure("embedder")
            logger.debug(f"Embedder health check failed: {e}")

    # Reranker
    if _should_skip_due_to_cooldown("reranker"):
        pass
    else:
        try:
            get_reranker()
            _model_status["reranker"] = "ready"
            _clear_failure("reranker")
        except Exception as e:
            _model_status["reranker"] = "error"
            _mark_failure("reranker")
            logger.debug(f"Reranker health check failed: {e}")

    # VLM
    if _should_skip_due_to_cooldown("vlm"):
        pass
    else:
        try:
            get_vlm()
            _model_status["vlm"] = "ready"
            _clear_failure("vlm")
        except Exception as e:
            _model_status["vlm"] = "error"
            _mark_failure("vlm")
            logger.debug(f"VLM health check failed: {e}")

    # UniParser 健康检查（通过环境变量配置 + 同样熔断）
    if _should_skip_due_to_cooldown("uniparser"):
        pass
    else:
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
                    _clear_failure("uniparser")
                else:
                    _model_status["uniparser"] = "error"
                    _mark_failure("uniparser")
            else:
                _model_status["uniparser"] = "error"
                # 缺配置不算"失败"，不熔断
        except Exception as e:
            _model_status["uniparser"] = "error"
            _mark_failure("uniparser")
            logger.debug(f"UniParser health check failed: {e}")

    # MolDet
    if _should_skip_due_to_cooldown("moldet"):
        pass
    else:
        try:
            pipeline = get_moldet()
            if pipeline and pipeline.is_available():
                _model_status["moldet"] = "ready"
                _clear_failure("moldet")
            else:
                _model_status["moldet"] = "error"
                _mark_failure("moldet")
        except Exception as e:
            _model_status["moldet"] = "error"
            _mark_failure("moldet")
            logger.debug(f"MolDet health check failed: {e}")

    # 计算整体状态（不再含 llm — 见模块 docstring）
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
    if status == "ready":
        _clear_failure(name)
