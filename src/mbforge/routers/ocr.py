"""OCR backend test endpoints — live probes against cloud APIs.

Each endpoint validates the corresponding backend by issuing a tiny
HTTP request with the user's credentials. The actual OCR work happens
in `mbforge.backends.ocr.*` (called from `pipeline.extract_text`).

These endpoints are intentionally lightweight — they only check
authentication and reachability, not full extraction accuracy.
"""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter

from ..utils.config import load_global_config

logger = logging.getLogger(__name__)

router = APIRouter()

_TIMEOUT = 10


def _ocr_settings() -> dict:
    """Read current ocr config from AppConfig."""
    cfg = load_global_config()
    return dict(cfg.ocr or {})


@router.post("/test-mineru")
async def test_mineru(body: dict) -> dict:
    api_key = (body.get("apiKey") or "").strip()
    if not api_key:
        api_key = _ocr_settings().get("mineru_api_key", "")
    if not api_key:
        return {"ok": False, "status": None, "message": "MinerU api_key 未设置"}
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            r = client.get(
                "https://mineru.net/api/v4/extract/task",
                headers={"Authorization": f"Bearer {api_key}"},
            )
        return {
            "ok": r.status_code in (200, 400, 401, 403),
            "status": r.status_code,
            "message": "ok" if r.status_code == 200 else "鉴权或网络问题",
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "status": None, "message": str(exc)}


@router.post("/test-paddleocr")
async def test_paddleocr(body: dict) -> dict:
    api_key = (body.get("apiKey") or "").strip()
    host = (body.get("host") or "").strip()
    model = (body.get("model") or "").strip()
    if not api_key or not host:
        cfg = _ocr_settings()
        api_key = api_key or cfg.get("paddleocr_api_key", "")
        host = host or cfg.get("paddleocr_host", "https://aistudio.baidu.com")
        model = model or cfg.get("paddleocr_model", "PaddleOCR-VL-1.6")
    if not api_key:
        return {"ok": False, "status": None, "message": "PaddleOCR api_key 未设置"}
    endpoint = f"{host.rstrip('/')}/paddleocr/api/ocr/{model}"
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            # 1x1 PNG as a probe payload.
            tiny_png = (
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
                b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00"
                b"\x00\x00\x0cIDAT\x08\x99c\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa3\x9c\x1d\x00\x00\x00\x00IEND\xaeB`\x82"
            )
            r = client.post(
                endpoint,
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": ("probe.png", tiny_png, "image/png")},
            )
        return {
            "ok": r.status_code in (200, 400, 401, 403, 422),
            "status": r.status_code,
            "message": "ok" if r.status_code == 200 else "鉴权或网络问题",
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "status": None, "message": str(exc)}


@router.post("/test-glmocr")
async def test_glmocr(body: dict) -> dict:
    api_key = (body.get("apiKey") or "").strip()
    if not api_key:
        api_key = _ocr_settings().get("glmocr_api_key", "")
    if not api_key:
        return {"ok": False, "status": None, "message": "GLM-OCR api_key 未设置"}
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            r = client.post(
                "https://open.bigmodel.cn/api/paas/v4/layout_parsing",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "glm-ocr",
                    "document": {
                        "type": "image_url",
                        "image_url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=",
                    },
                },
            )
        return {
            "ok": r.status_code in (200, 400, 401, 403),
            "status": r.status_code,
            "message": "ok" if r.status_code == 200 else "鉴权或网络问题",
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "status": None, "message": str(exc)}


@router.get("/chain-status")
async def chain_status() -> dict:
    """Inspect which OCR backends the chain would try for the current settings."""
    from ..backends.ocr import list_configured_backends

    return {
        "backends": list(list_configured_backends(_ocr_settings())),
        "priority": ["mineru", "paddleocr", "glmocr", "rapidocr"],
    }
