"""Document processing pipeline endpoints."""

from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter

from ..utils.logger import get_logger

logger = get_logger("mbforge.pipeline_router")

router = APIRouter()


@router.post("/enqueue")
async def pipeline_enqueue(body: dict) -> dict:
    root = body.get("project_root", "")
    file_path = body.get("file_path", "")
    if not root or not file_path:
        return {"success": False, "error": "project_root and file_path required"}
    task_id = str(uuid.uuid4())
    doc_id = body.get("doc_id", "")
    # Run pipeline in background
    asyncio.get_event_loop().run_in_executor(
        None, _run_pipeline_sync, file_path, root, doc_id or task_id
    )
    return {"success": True, "task_id": task_id}


def _run_pipeline_sync(pdf_path: str, project_root: str, doc_id: str):
    try:
        from ..pipeline.runner import run_pipeline

        run_pipeline(pdf_path, project_root, doc_id=doc_id)
    except Exception as e:
        logger.error("Pipeline failed for %s: %s", pdf_path, e)


@router.post("/process")
async def pipeline_process(body: dict) -> dict:
    """Synchronous pipeline execution (blocks until complete)."""
    root = body.get("project_root", "")
    file_path = body.get("file_path", "")
    doc_id = body.get("doc_id", "")
    chunk_size = body.get("chunk_size", 512)
    chunk_overlap = body.get("chunk_overlap", 128)
    if not root or not file_path:
        return {"success": False, "error": "project_root and file_path required"}
    try:
        from ..pipeline.runner import run_pipeline

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            lambda: run_pipeline(file_path, root, doc_id=doc_id, chunk_size=chunk_size, chunk_overlap=chunk_overlap),
        )
        return {
            "success": True,
            "doc_id": result.doc_id,
            "page_count": result.page_count,
            "section_count": result.section_count,
            "chunk_count": result.chunk_count,
            "indexed_count": result.indexed_count,
            "parser": result.parser,
            "title": result.title,
            "duration_ms": result.duration_ms,
        }
    except Exception as e:
        logger.error("Pipeline failed: %s", e)
        return {"success": False, "error": str(e)}


@router.post("/queue")
async def pipeline_queue(body: dict) -> dict:
    root = body.get("project_root", "")
    if not root:
        return {"success": True, "tasks": []}
    from ..core.database import DatabaseManager

    db = DatabaseManager(root)
    with db.kb_conn() as conn:
        rows = conn.execute("SELECT * FROM ingest_queue ORDER BY created_at DESC").fetchall()
        tasks = [dict(r) for r in rows]
    return {"success": True, "tasks": tasks}


@router.post("/queue/stats")
async def pipeline_queue_stats(body: dict) -> dict:
    root = body.get("project_root", "")
    if not root:
        return {"success": True, "stats": {}}
    from ..core.database import DatabaseManager

    db = DatabaseManager(root)
    with db.kb_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM ingest_queue").fetchone()[0]
        by_status = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM ingest_queue GROUP BY status"
        ).fetchall()
    return {"success": True, "stats": {"total": total, "by_status": {r["status"]: r["cnt"] for r in by_status}}}


@router.post("/queue/{task_id}/cancel")
async def pipeline_cancel(task_id: str) -> dict:
    return {"success": True}


@router.post("/queue/{task_id}/retry")
async def pipeline_retry(task_id: str) -> dict:
    return {"success": True}
