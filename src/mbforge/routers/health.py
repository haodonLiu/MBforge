"""Health check and sidecar status endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from ..core.resource_manager import ResourceManager

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    from ..backends import moldet, molscribe

    statuses = {}
    for name, mod in [("moldet", moldet), ("molscribe", molscribe)]:
        try:
            h = mod.health()
            statuses[name] = h.get("status", "unknown")
        except Exception:
            statuses[name] = "error"

    overall = "online" if all(s == "ready" for s in statuses.values()) else "partial"
    return {"status": overall, "models": statuses, "resources": {}}


@router.get("/sidecar/status")
async def sidecar_status() -> dict:
    report = ResourceManager.check_all()
    return {
        "healthy": all(r.status.value == "ready" for r in report.resources),
        "state": "online",
        "restart_count": 0,
        "uptime_secs": 0,
        "last_error": None,
    }


@router.post("/sidecar/restart")
async def sidecar_restart() -> dict:
    """Sidecar restart stub (not needed in pure web mode)."""
    return {"success": True}


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
