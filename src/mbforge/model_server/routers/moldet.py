"""MolDet 分子检测与识别路由."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Request

from ...utils.exceptions import ModelNotAvailableError, ValidationError
from ...utils.helpers import decode_base64_image
from ...utils.logger import get_logger
from ..models.moldet import get_moldet
from .health import set_model_status

logger = get_logger(__name__)
router = APIRouter()


@router.post("/detect-page")
async def detect_page(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
        image_base64 = body.get("image_base64", "")
        if not image_base64:
            raise ValidationError("image_base64 is required")

        image = decode_base64_image(image_base64)
        pipeline = get_moldet()
        if pipeline is None or not pipeline.is_available():
            raise ModelNotAvailableError("MolDet pipeline not available")

        loop = asyncio.get_running_loop()
        boxes = await loop.run_in_executor(
            None, lambda: pipeline.doc_detector.detect(image)
        )
        set_model_status("moldet", "ready")
        return {
            "boxes": [
                {"x1": x1, "y1": y1, "x2": x2, "y2": y2, "conf": conf}
                for x1, y1, x2, y2, conf in boxes
            ],
            "count": len(boxes),
        }
    except (ValidationError, ModelNotAvailableError):
        raise
    except Exception as e:
        set_model_status("moldet", "error")
        logger.error(f"MolDet detect-page failed: {e}", exc_info=True)
        raise ModelNotAvailableError(str(e))


@router.post("/extract-page")
async def extract_page(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
        image_base64 = body.get("image_base64", "")
        if not image_base64:
            raise ValidationError("image_base64 is required")

        page_idx = body.get("page_idx", 0)
        page_w_pts = body.get("page_w_pts", 595.0)
        page_h_pts = body.get("page_h_pts", 842.0)
        image_w = body.get("image_w", 0)
        image_h = body.get("image_h", 0)
        dpi = body.get("dpi", 300.0)

        if image_w == 0 or image_h == 0:
            raise ValidationError("image_w and image_h are required")

        image = decode_base64_image(image_base64)

        pipeline = get_moldet()
        if pipeline is None or not pipeline.is_available():
            raise ModelNotAvailableError("MolDet pipeline not available")

        loop = asyncio.get_running_loop()
        results = await loop.run_in_executor(
            None, lambda: pipeline.extract_page(
                image, page_idx, page_w_pts, page_h_pts, image_w, image_h, dpi
            )
        )
        set_model_status("moldet", "ready")
        return {
            "results": [r.to_dict() for r in results],
            "count": len(results),
        }
    except (ValidationError, ModelNotAvailableError):
        raise
    except Exception as e:
        set_model_status("moldet", "error")
        logger.error(f"MolDet extract-page failed: {e}", exc_info=True)
        raise ModelNotAvailableError(str(e))
