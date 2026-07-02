"""MolScribe structure recognition endpoints."""

from __future__ import annotations

import asyncio
import os
from typing import Any

from fastapi import APIRouter, Request

from ..backends import molscribe
from ..server_state import set_model_status
from ..utils.helpers import (
    ModelNotAvailableError,
    ValidationError,
    decode_base64_to_tempfile,
)
from ..utils.logger import get_logger

logger = get_logger("mbforge.molscribe_api_router")

router = APIRouter()


@router.post("")
async def molscribe_predict(request: Request) -> dict[str, Any]:
    """Predict SMILES from molecule image."""
    tmp_path = None
    try:
        import numpy as np
        from PIL import Image

        content_type = request.headers.get("content-type", "")

        if content_type == "application/octet-stream":
            width = int(request.headers.get("x-image-width", "0"))
            height = int(request.headers.get("x-image-height", "0"))
            if width <= 0 or height <= 0:
                raise ValidationError("X-Image-Width and X-Image-Height required")
            raw_bytes = await request.body()
            arr = np.frombuffer(raw_bytes, dtype=np.uint8).reshape(height, width)
            image = Image.fromarray(arr, "L")
        else:
            body = await request.json()
            image_base64 = body.get("image_base64", "")
            if not image_base64:
                raise ValidationError("image_base64 is required")
            ext = body.get("ext", "png")
            tmp_path = decode_base64_to_tempfile(image_base64, ext)
            image = Image.open(tmp_path)

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, molscribe.load)
        result = await loop.run_in_executor(None, lambda: molscribe.predict(image))
        if not result.esmiles:
            err_msg = result.properties.get("error", "unknown error")
            raise ModelNotAvailableError(f"MolScribe not available: {err_msg}")
        set_model_status("molscribe", "ready")
        return {
            "esmiles": result.esmiles,
            "confidence": result.scribe_conf,
            "success": True,
        }
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
