"""Resource management endpoints — catalog, download, status, cache."""

from __future__ import annotations

from fastapi import APIRouter

from ..core.resource_manager import ResourceManager

router = APIRouter()


@router.post("/resource/download")
async def resource_download(body: dict) -> dict:
    resource_id = body.get("resource_id", "")
    if not resource_id:
        return {"success": False, "error": "resource_id required"}
    result = ResourceManager.ensure(resource_id)
    return {"success": result.status.value == "ready", "status": result.status.value}


@router.post("/resource/cache-dir-info")
async def cache_dir_info() -> dict:
    from ..utils.paths import get_model_cache_dir
    cache_dir = get_model_cache_dir()
    return {
        "mbforge": {"path": cache_dir, "exists": True, "size_mb": 0},
        "huggingface": {"path": "", "exists": False, "size_mb": 0, "env_var": "HF_HOME"},
        "modelscope": {"path": "", "exists": False, "size_mb": 0, "env_var": "MODELSCOPE_CACHE"},
    }


@router.post("/resource/delete")
async def resource_delete(body: dict) -> dict:
    return {"success": True}


@router.post("/resource/delete-subfile")
async def resource_delete_subfile(body: dict) -> dict:
    return {"success": True}


@router.post("/resource/download-subfile")
async def resource_download_subfile(body: dict) -> dict:
    return {"success": True, "path": ""}


@router.post("/resource/test")
async def resource_test(body: dict) -> dict:
    return {"ok": True, "error": "", "duration_ms": 0}


@router.post("/resources/check")
async def resources_check() -> dict:
    report = ResourceManager.check_all()
    return {
        "resources": [
            {"id": r.id, "name": r.name, "status": r.status.value, "local_path": r.local_path}
            for r in report.resources
        ]
    }


@router.post("/resources/status")
async def resources_status(body: dict) -> dict:
    resource_id = body.get("resource_id", "")
    report = ResourceManager.check_all()
    for r in report.resources:
        if r.id == resource_id:
            return {
                "status": r.status.value,
                "local_path": r.local_path,
                "size_mb": r.size_mb,
                "expected_path": r.local_path,
                "subfiles": [],
            }
    return {"status": "missing", "local_path": "", "size_mb": 0, "expected_path": "", "subfiles": []}


@router.post("/resources/model-path")
async def resources_model_path(body: dict) -> dict:
    resource_id = body.get("resource_id", "")
    report = ResourceManager.check_all()
    for r in report.resources:
        if r.id == resource_id:
            return {"success": True, "path": r.local_path}
    return {"success": False, "path": None}


@router.post("/resources/catalog")
async def resources_catalog() -> dict:
    report = ResourceManager.check_all()
    return {"resources": [
        {
            "id": r.id,
            "name": r.name,
            "type": "model",
            "description": "",
            "ms_repo": "",
            "license": "",
            "size_mb": r.size_mb,
        }
        for r in report.resources
    ]}


@router.post("/resources/refresh-paths")
async def refresh_paths() -> dict:
    return {"success": True, "resources": {}}
