"""VLM 推理路由."""

from __future__ import annotations

import asyncio
import os

from fastapi import APIRouter, Request

from ...utils.exceptions import ModelNotAvailableError, ValidationError
from ...utils.helpers import decode_base64_to_tempfile
from ...utils.logger import get_logger
from ..models.moldet import get_moldet
from ..models.vlm import get_vlm
from .health import set_model_status

logger = get_logger(__name__)
router = APIRouter()


@router.post("/describe")
async def describe(request: Request) -> dict:
    tmp_path = None
    try:
        body = await request.json()
        image_base64 = body.get("image_base64", "")
        prompt = body.get("prompt", "")

        if not image_base64:
            raise ValidationError("image_base64 is required")

        ext = body.get("ext", "png")
        tmp_path = decode_base64_to_tempfile(image_base64, ext)

        vlm = get_vlm()
        loop = asyncio.get_running_loop()
        description = await loop.run_in_executor(
            None, lambda: vlm.describe_image(tmp_path, prompt=prompt)
        )
        set_model_status("vlm", "ready")
        return {"description": description}
    except (ValidationError, ModelNotAvailableError):
        raise
    except Exception as e:
        set_model_status("vlm", "error")
        logger.error(f"VLM describe failed: {e}", exc_info=True)
        raise ModelNotAvailableError(str(e))
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


@router.post("/molscribe")
async def molscribe(request: Request) -> dict:
    """化学结构图像 → SMILES（MolScribe）. Uses standalone molscribe module."""
    tmp_path = None
    try:
        body = await request.json()
        image_base64 = body.get("image_base64", "")

        if not image_base64:
            raise ValidationError("image_base64 is required")

        ext = body.get("ext", "png")
        tmp_path = decode_base64_to_tempfile(image_base64, ext)

        from PIL import Image
        from ...parsers.molecule.molscribe import MolScribe

        image = Image.open(tmp_path)
        model = MolScribe()
        if not model.is_available:
            raise ModelNotAvailableError(f"MolScribe not available: {model.error}")

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, lambda: model.predict(image))

        set_model_status("vlm", "ready")
        return {
            "esmiles": result.esmiles,
            "confidence": result.confidence,
            "success": result.success and bool(result.esmiles),
        }
    except (ValidationError, ModelNotAvailableError):
        raise
    except Exception as e:
        set_model_status("vlm", "error")
        logger.error(f"MolScribe predict failed: {e}", exc_info=True)
        raise ModelNotAvailableError(str(e))
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
