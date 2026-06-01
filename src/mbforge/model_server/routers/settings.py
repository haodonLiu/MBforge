"""Settings 管理路由."""

from __future__ import annotations
from typing import Any

from fastapi import APIRouter, Request

from ...utils.config import AppConfig, load_global_config, save_global_config
from ...utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.get("/")
async def get_settings() -> dict[str, Any]:
    try:
        config = load_global_config()
        return {"success": True, "settings": config.to_dict()}
    except Exception as e:
        logger.error(f"Failed to load settings: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@router.post("/")
async def save_settings(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
        settings = body.get("settings", {})
        config = AppConfig.from_dict(settings)
        save_global_config(config)
        return {"success": True}
    except Exception as e:
        logger.error(f"Failed to save settings: {e}", exc_info=True)
        return {"success": False, "error": str(e)}
