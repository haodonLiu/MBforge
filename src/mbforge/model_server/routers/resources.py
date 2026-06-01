"""统一资源管理路由 — 环境检查 + 资源下载 + 全量搭建.

基于 ResourceManager 提供环境全貌的 API。
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from ...core.resource_manager import (
    RESOURCE_CATALOG, ResourceManager, ResourceType, ResourceStatus,
)

logger = logging.getLogger("mbforge.resources")
router = APIRouter()


@router.get("/check")
async def check_all() -> dict:
    """全量环境检查 — 返回所有资源状态 + 环境信息."""
    try:
        report = ResourceManager.check_all()
        return {
            "success": True,
            "python_version": report.python_version,
            "gpu_available": report.gpu_available,
            "gpu_name": report.gpu_name,
            "cuda_version": report.cuda_version,
            "summary": report.summary,
            "resources": [
                {
                    "id": r.id,
                    "name": r.name,
                    "type": r.type.value,
                    "status": r.status.value,
                    "local_path": r.local_path,
                    "size_mb": r.size_mb,
                    "version": r.version,
                    "error": r.error,
                }
                for r in report.resources
            ],
        }
    except Exception as e:
        logger.error(f"Resource check failed: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@router.get("/catalog")
async def get_catalog() -> dict:
    """获取资源目录（不含状态，纯元数据）."""
    try:
        items = []
        for rid, info in RESOURCE_CATALOG.items():
            items.append({
                "id": info.id,
                "name": info.name,
                "type": info.type.value,
                "description": info.description,
                "size_mb": info.size_mb,
                "license": info.license,
                "license_url": info.license_url,
                "ms_repo": info.ms_repo,
                "source_url": info.source_url,
                "pip_name": info.pip_name,
            })
        return {"success": True, "catalog": items}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/status/{resource_id}")
async def check_one(resource_id: str) -> dict:
    """检查单个资源状态."""
    try:
        status = ResourceManager.check(resource_id)
        info = RESOURCE_CATALOG.get(resource_id)
        return {
            "success": True,
            "resource": {
                "id": status.id,
                "name": status.name,
                "type": status.type.value,
                "status": status.status.value,
                "local_path": status.local_path,
                "size_mb": status.size_mb,
                "version": status.version,
                "error": status.error,
                "description": info.description if info else "",
            },
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/ensure/{resource_id}")
async def ensure_resource(resource_id: str):
    """确保单个资源可用（SSE 流式进度）."""
    if resource_id not in RESOURCE_CATALOG:
        return {"success": False, "error": f"未知资源: {resource_id}"}

    # 先检查是否已就绪
    status = ResourceManager.check(resource_id)
    if status.status == ResourceStatus.READY:
        return {"success": True, "status": "already_ready", "resource": _status_to_dict(status)}

    def event_stream():
        def callback(event: dict):
            # 通过 closure 将事件传入 SSE 流
            pass

        try:
            yield f"data: {json.dumps({'status': 'starting', 'resource_id': resource_id}, ensure_ascii=False)}\n\n"

            # 使用 ResourceManager.ensure（同步，会阻塞）
            events = []
            def capture_callback(event: dict):
                events.append(event)
                # 无法在这里 yield，因为 ensure 是同步的

            result = ResourceManager.ensure(resource_id, callback=capture_callback)

            # 回放所有事件
            for evt in events:
                yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"

            yield f"data: {json.dumps({'status': 'completed' if result.status == ResourceStatus.READY else 'failed', 'resource': _status_to_dict(result)}, ensure_ascii=False)}\n\n"

        except Exception as e:
            logger.error(f"Ensure resource {resource_id} failed: {e}", exc_info=True)
            yield f"data: {json.dumps({'status': 'failed', 'error': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.post("/ensure-all")
async def ensure_all():
    """一键搭建全部环境（SSE 流式进度）."""
    def event_stream():
        try:
            report = ResourceManager.check_all()
            total = len(report.resources)
            ready = sum(1 for r in report.resources if r.status == ResourceStatus.READY)
            yield f"data: {json.dumps({'status': 'starting', 'total': total, 'already_ready': ready}, ensure_ascii=False)}\n\n"

            for res in report.resources:
                if res.status == ResourceStatus.READY:
                    yield f"data: {json.dumps({'status': 'skip', 'resource_id': res.id, 'name': res.name, 'reason': 'already_ready'}, ensure_ascii=False)}\n\n"
                    continue

                info = RESOURCE_CATALOG.get(res.id)
                if info is None:
                    continue

                yield f"data: {json.dumps({'status': 'ensuring', 'resource_id': res.id, 'name': res.name}, ensure_ascii=False)}\n\n"

                try:
                    result = ResourceManager.ensure(res.id)
                    yield f"data: {json.dumps({'status': 'done' if result.status == ResourceStatus.READY else 'failed', 'resource_id': res.id, 'name': res.name, 'resource': _status_to_dict(result)}, ensure_ascii=False)}\n\n"
                except Exception as e:
                    yield f"data: {json.dumps({'status': 'failed', 'resource_id': res.id, 'name': res.name, 'error': str(e)}, ensure_ascii=False)}\n\n"

            # 最终报告
            final_report = ResourceManager.check_all()
            yield f"data: {json.dumps({'status': 'finished', 'summary': final_report.summary}, ensure_ascii=False)}\n\n"

        except Exception as e:
            logger.error(f"Ensure-all failed: {e}", exc_info=True)
            yield f"data: {json.dumps({'status': 'failed', 'error': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


def _status_to_dict(status) -> dict:
    return {
        "id": status.id,
        "name": status.name,
        "type": status.type.value if hasattr(status.type, 'value') else str(status.type),
        "status": status.status.value if hasattr(status.status, 'value') else str(status.status),
        "local_path": status.local_path,
        "size_mb": status.size_mb,
        "version": status.version,
        "error": status.error,
    }
