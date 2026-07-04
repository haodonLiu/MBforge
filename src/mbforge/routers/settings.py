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


@router.get("")
async def settings_get() -> dict:
    cfg = load_global_config()
    return {"success": True, "settings": cfg.model_dump()}


@router.put("")
async def settings_update(body: dict[str, Any]) -> dict:
    """局部更新:deep-merge → 校验 → 持久化."""
    try:
        new_cfg = update_settings(body)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    return {"success": True, "settings": new_cfg.model_dump()}


@router.post("/reset")
async def settings_reset() -> dict:
    """重置全部设置为默认值."""
    cfg = reset_settings()
    return {"success": True, "settings": cfg.model_dump()}


# TODO: cache-size / cache-clear 真正接到 core.semantic_cache
@router.post("/cache-size")
async def cache_size(body: dict) -> dict:
    """Stub — 真正实现待接入 core.semantic_cache."""
    return {"success": True, "size_mb": 0, "count": 0}


@router.post("/cache-clear")
async def cache_clear(body: dict) -> dict:
    """Stub — 真正实现待接入 core.semantic_cache."""
    return {"success": True, "cleared": 0}
