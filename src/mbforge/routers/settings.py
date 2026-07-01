"""Settings endpoints."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("")
async def settings_get() -> dict:
    from ..utils.config import load_global_config

    cfg = load_global_config()
    return {"success": True, "settings": cfg.model_dump()}


@router.put("")
async def settings_update(body: dict) -> dict:
    from ..utils.config import load_global_config, save_global_config

    cfg = load_global_config()
    data = cfg.model_dump()

    def deep_merge(base: dict, override: dict) -> dict:
        for k, v in override.items():
            if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                deep_merge(base[k], v)
            else:
                base[k] = v
        return base

    deep_merge(data, body)
    from ..utils.config import AppConfig
    new_cfg = AppConfig.model_validate(data)
    save_global_config(new_cfg)
    return {"success": True}


@router.post("/cache-size")
async def cache_size(body: dict) -> dict:
    """返回缓存大小信息."""
    return {"success": True, "size_mb": 0, "count": 0}


@router.post("/cache-clear")
async def cache_clear(body: dict) -> dict:
    """清除缓存."""
    return {"success": True, "cleared": 0}
