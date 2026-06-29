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
    data.update(body)
    from ..utils.config import AppConfig
    new_cfg = AppConfig.model_validate(data)
    save_global_config(new_cfg)
    return {"success": True}
