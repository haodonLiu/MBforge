"""Model testing and management endpoints."""

from __future__ import annotations

import asyncio
import base64
import io
import time
from typing import Any

from fastapi import APIRouter

from ..utils.logger import get_logger

logger = get_logger("mbforge.models_router")

router = APIRouter()


def _test_model_sync(model_id: str, subpath: str | None = None) -> dict[str, Any]:
    """Test a model by loading and running inference (sync)."""
    start = time.perf_counter()
    try:
        if model_id == "moldet":
            from ..backends.moldet_v2_ft import MolDetv2FTDetector
            detector = MolDetv2FTDetector()
            if not detector.is_available():
                return {"ok": False, "error": "Model not loaded", "duration_ms": 0}
            import numpy as np
            _ = detector.detect(np.zeros((960, 960, 3), dtype=np.uint8))
        elif model_id == "molscribe":
            from ..backends.molscribe import load as load_molscribe
            load_molscribe()
        else:
            return {"ok": False, "error": f"Unknown model: {model_id}", "duration_ms": 0}

        duration_ms = int((time.perf_counter() - start) * 1000)
        return {"ok": True, "error": "", "duration_ms": duration_ms}
    except Exception as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        logger.error("Model test failed for %s: %s", model_id, e)
        return {"ok": False, "error": str(e), "duration_ms": duration_ms}


@router.post("/test")
async def test_model(body: dict) -> dict:
    """Test a model by loading and running inference."""
    model_id = body.get("model_id", "")
    subpath = body.get("subpath")
    if not model_id:
        return {"success": False, "error": "model_id required"}

    result = await asyncio.to_thread(_test_model_sync, model_id, subpath)
    return {"success": True, **result}


def _render_molecule_sync(smiles: str, width: int, height: int) -> dict:
    """Render a molecule to SVG/PNG (sync)."""
    try:
        from rdkit import Chem
        from rdkit.Chem import Draw

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return {"success": False, "error": "Invalid SMILES"}

        img = Draw.MolToImage(mol, size=(width, height))
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        img_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
        return {"success": True, "image_base64": img_b64}
    except Exception as e:
        logger.error("Molecule render failed: %s", e)
        return {"success": False, "error": str(e)}


@router.post("/mol/render")
async def render_molecule(body: dict) -> dict:
    """Render a molecule to SVG/PNG."""
    smiles = body.get("smiles", "")
    width = int(body.get("width", 300) or 300)
    height = int(body.get("height", 200) or 200)

    if not smiles:
        return {"success": False, "error": "smiles required"}

    return await asyncio.to_thread(_render_molecule_sync, smiles, width, height)
