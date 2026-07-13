"""Molecule rendering endpoints (RDKit-backed).

Mounted on the main app at /api/v1/models so the frontend hits it
directly instead of being routed through the model_server sub-app
mounted at the same prefix (whose routers carry an extra /api/v1
segment that breaks POST /api/v1/models/mol/render with a 404).

FastAPI resolves include_router(...) routes before Mount(...), so
this router takes priority over the sidecar for paths it owns.
Other sidecar paths (molscribe/*, pdf/*, test, health) keep going
through the mount.
"""

from __future__ import annotations

import asyncio
import base64
import io
import logging

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter()


def _render_molecule_sync(smiles: str, width: int, height: int) -> dict:
    """Render a SMILES string to a base64 PNG via RDKit (sync)."""
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
    except Exception as exc:  # noqa: BLE001
        logger.error("Molecule render failed for smiles=%r: %s", smiles, exc)
        return {"success": False, "error": str(exc)}


@router.post("/mol/render")
async def render_molecule(body: dict) -> dict:
    """Render a SMILES string to a base64 PNG via RDKit."""
    smiles = body.get("smiles", "")
    width = int(body.get("width", 300) or 300)
    height = int(body.get("height", width) or width)

    if not smiles:
        return {"success": False, "error": "smiles required"}

    return await asyncio.to_thread(_render_molecule_sync, smiles, width, height)
