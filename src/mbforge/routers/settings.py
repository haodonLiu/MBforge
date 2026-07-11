"""Settings endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from ..utils.config import (
    load_global_config,
    reset_settings,
    update_settings,
)

router = APIRouter()


def _is_secret_key(key: str) -> bool:
    """Return True if ``key`` looks like it holds a credential."""
    lower = key.lower()
    return any(
        suffix in lower
        for suffix in ("api_key", "secret", "token", "password", "_key")
    )


def _redact_secrets(obj: Any) -> Any:
    """Recursively replace secret-ish values with '***' for GET responses."""
    if isinstance(obj, dict):
        return {
            k: "***" if isinstance(v, str) and _is_secret_key(k) else _redact_secrets(v)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_redact_secrets(v) for v in obj]
    return obj


@router.get("")
async def settings_get() -> dict:
    cfg = load_global_config()
    return {"success": True, "settings": _redact_secrets(cfg.model_dump())}


@router.put("")
async def settings_update(body: dict[str, Any]) -> dict:
    """局部更新:deep-merge → 校验 → 持久化."""
    try:
        new_cfg = update_settings(body)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    return {"success": True, "settings": _redact_secrets(new_cfg.model_dump())}


@router.post("/reset")
async def settings_reset() -> dict:
    """重置全部设置为默认值."""
    cfg = reset_settings()
    return {"success": True, "settings": _redact_secrets(cfg.model_dump())}


# TODO: cache-size / cache-clear 真正接到 core.semantic_cache
@router.post("/cache-size")
async def cache_size(body: dict) -> dict:
    """Stub — 真正实现待接入 core.semantic_cache."""
    return {"success": True, "size_mb": 0, "count": 0}


@router.post("/cache-clear")
async def cache_clear(body: dict) -> dict:
    """Stub — 真正实现待接入 core.semantic_cache."""
    return {"success": True, "cleared": 0}
