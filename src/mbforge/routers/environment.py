"""Environment and resource management endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from ..core.resource_manager import ResourceManager

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    from ..backends import moldet, molscribe, qwen3_embed, zvec

    statuses = {}
    for name, mod in [("embedder", qwen3_embed), ("moldet", moldet), ("molscribe", molscribe), ("zvec", zvec)]:
        try:
            h = mod.health()
            statuses[name] = h.get("status", "unknown")
        except Exception:
            statuses[name] = "error"

    overall = "online" if all(s == "ready" for s in statuses.values()) else "partial"
    return {"status": overall, "models": statuses, "resources": {}}


@router.get("/environment/check")
async def environment_check() -> dict:
    report = ResourceManager.check_all()
    return {
        "python_version": report.python_version,
        "gpu_available": report.gpu_available,
        "gpu_name": report.gpu_name,
        "cuda_version": report.cuda_version,
        "resources": [
            {
                "id": r.id,
                "name": r.name,
                "status": r.status.value,
                "local_path": r.local_path,
                "size_mb": r.size_mb,
            }
            for r in report.resources
        ],
    }


@router.post("/resource/download")
async def resource_download(body: dict) -> dict:
    resource_id = body.get("resource_id", "")
    if not resource_id:
        return {"success": False, "error": "resource_id required"}
    result = ResourceManager.ensure(resource_id)
    return {"success": result.status.value == "ready", "status": result.status.value}


@router.post("/resources/check")
async def resources_check() -> dict:
    report = ResourceManager.check_all()
    return {
        "resources": [
            {"id": r.id, "name": r.name, "status": r.status.value, "local_path": r.local_path}
            for r in report.resources
        ]
    }
