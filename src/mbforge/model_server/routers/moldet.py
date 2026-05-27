"""MolDet 分子检测与识别路由."""

from __future__ import annotations

import base64
from io import BytesIO

import numpy as np
from fastapi import APIRouter, Request
from PIL import Image

from ...utils.exceptions import ModelNotAvailableError, ValidationError
from ...utils.logger import get_logger
from ..models.moldet import get_moldet
from .health import set_model_status

logger = get_logger(__name__)
router = APIRouter()


def _decode_image(image_base64: str) -> Image.Image:
    data = base64.b64decode(image_base64)
    return Image.open(BytesIO(data))


@router.post("/detect-page")
async def detect_page(request: Request) -> dict:
    try:
        body = await request.json()
        image_base64 = body.get("image_base64", "")
        if not image_base64:
            raise ValidationError("image_base64 is required")

        image = _decode_image(image_base64)
        pipeline = get_moldet()
        if pipeline is None or not pipeline.is_available():
            raise ModelNotAvailableError("MolDet pipeline not available")

        boxes = pipeline.doc_detector.detect(image)
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
async def extract_page(request: Request) -> dict:
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

        image = _decode_image(image_base64)
        arr = np.array(image)
        h, w = arr.shape[:2]
        if image_w == 0:
            image_w = w
        if image_h == 0:
            image_h = h

        pipeline = get_moldet()
        if pipeline is None or not pipeline.is_available():
            raise ModelNotAvailableError("MolDet pipeline not available")

        results = pipeline.extract_page(
            image, page_idx, page_w_pts, page_h_pts, image_w, image_h, dpi
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


@router.post("/extract-region")
async def extract_region(request: Request) -> dict:
    try:
        body = await request.json()
        image_base64 = body.get("image_base64", "")
        if not image_base64:
            raise ValidationError("image_base64 is required")

        page_idx = body.get("page_idx", 0)
        bbox_pdf = body.get("bbox_pdf")

        image = _decode_image(image_base64)
        pipeline = get_moldet()
        if pipeline is None or not pipeline.is_available():
            raise ModelNotAvailableError("MolDet pipeline not available")

        result = pipeline.extract_region(
            image, page_idx, tuple(bbox_pdf) if bbox_pdf else None
        )
        set_model_status("moldet", "ready")
        return {"result": result.to_dict()}
    except (ValidationError, ModelNotAvailableError):
        raise
    except Exception as e:
        set_model_status("moldet", "error")
        logger.error(f"MolDet extract-region failed: {e}", exc_info=True)
        raise ModelNotAvailableError(str(e))


@router.get("/health")
async def moldet_health() -> dict:
    try:
        pipeline = get_moldet()
        available = pipeline is not None and pipeline.is_available()
        status = "ready" if available else "loading"
        set_model_status("moldet", status)
        return {
            "status": status,
            "doc_detector": pipeline.doc_detector.is_available() if pipeline else False,
            "general_detector": pipeline.general_detector.is_available() if pipeline else False,
            "recognizer": pipeline.recognizer.is_available() if pipeline else False,
        }
    except Exception as e:
        set_model_status("moldet", "error")
        logger.error(f"MolDet health check failed: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}
