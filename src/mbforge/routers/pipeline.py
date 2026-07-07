"""Document processing pipeline endpoints."""

from __future__ import annotations

import asyncio
import uuid
from concurrent.futures import Future

from fastapi import APIRouter

from ..utils.logger import get_logger
from ..utils.helpers import resolve_root

logger = get_logger("mbforge.pipeline_router")

router = APIRouter()

# Track background futures for error reporting
_background_futures: dict[str, Future] = {}


@router.post("/enqueue")
async def pipeline_enqueue(body: dict) -> dict:
    root = resolve_root(body)
    action = body.get("action", "")

    if action == "enqueue_unresolved":
        if not root:
            return {"success": False, "error": "library_root required"}
        enqueued = _enqueue_all_unresolved(root)
        return {"success": True, "enqueued": enqueued}

    file_path = body.get("file_path", "")
    if not root or not file_path:
        return {"success": False, "error": "library_root and file_path required"}
    task_id = str(uuid.uuid4())
    doc_id = body.get("doc_id", "")
    loop = asyncio.get_running_loop()
    future = loop.run_in_executor(
        None, _run_pipeline_sync, file_path, root, doc_id or task_id
    )
    _background_futures[task_id] = future
    future.add_done_callback(lambda f: _background_futures.pop(task_id, None))
    return {"success": True, "task_id": task_id}


def _enqueue_all_unresolved(root: str) -> int:
    """扫描项目中所有未处理的 PDF 并入队，返回入队数量."""
    from pathlib import Path

    from ..core.database import DatabaseManager
    from ..core.project import scan_project_files

    db = DatabaseManager.get(root)
    files = scan_project_files(root)
    pdf_files = [f for f in files if f.lower().endswith(".pdf")]

    enqueued = 0
    with db.kb_conn() as conn:
        for rel_path in pdf_files:
            full_path = str(Path(root) / rel_path)
            # 检查是否已在队列中
            existing = conn.execute(
                "SELECT id FROM ingest_queue WHERE file_path = ?", (full_path,)
            ).fetchone()
            if existing:
                continue
            task_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO ingest_queue (id, file_path, project_root, status, created_at) VALUES (?, ?, ?, 'pending', datetime('now'))",
                (task_id, full_path, root),
            )
            enqueued += 1
            # 后台运行 pipeline
            loop = asyncio.get_running_loop()
            future = loop.run_in_executor(
                None, _run_pipeline_sync, full_path, root, task_id
            )
            _background_futures[task_id] = future
            future.add_done_callback(lambda f, tid=task_id: _background_futures.pop(tid, None))
    return enqueued


def _run_pipeline_sync(pdf_path: str, library_root: str, doc_id: str):
    try:
        from ..pipeline.runner import run_pipeline

        run_pipeline(pdf_path, library_root, doc_id=doc_id)
    except Exception as e:
        logger.error("Pipeline failed for %s: %s", pdf_path, e, exc_info=True)
        # Update task status in database
        try:
            from ..core.database import DatabaseManager
            db = DatabaseManager.get(project_root)
            with db.kb_conn() as conn:
                conn.execute(
                    "UPDATE ingest_queue SET status = 'failed', error = ? WHERE id = ?",
                    (str(e), doc_id),
                )
        except Exception:
            logger.error("Failed to update task status for %s", doc_id)


@router.post("/process")
async def pipeline_process(body: dict) -> dict:
    """Synchronous pipeline execution (blocks until complete)."""
    root = resolve_root(body)
    file_path = body.get("file_path", "")
    doc_id = body.get("doc_id", "")
    if not root or not file_path:
        return {"success": False, "error": "library_root and file_path required"}
    try:
        from ..pipeline.runner import run_pipeline

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            lambda: run_pipeline(file_path, root, doc_id=doc_id),
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
    root = resolve_root(body)
    if not root:
        return {"success": True, "tasks": []}
    from ..core.database import DatabaseManager

    db = DatabaseManager.get(root)
    try:
        with db.kb_conn() as conn:
            rows = conn.execute("SELECT * FROM ingest_queue ORDER BY created_at DESC").fetchall()
            tasks = [dict(r) for r in rows]
        return {"success": True, "tasks": tasks}
    except Exception as e:
        logger.warning("Failed to fetch queue: %s", e)
        return {"success": True, "tasks": []}


@router.get("/worker/status")
async def worker_status() -> dict:
    """检查后端 worker 状态 — FastAPI 服务在线即 worker 在线."""
    import time
    return {"status": "online", "ts": int(time.time())}


@router.post("/queue/stats")
async def pipeline_queue_stats(body: dict) -> dict:
    root = body.get("project_root", "")
    if not root:
        return {"success": True, "stats": {}}
    from ..core.database import DatabaseManager

    db = DatabaseManager.get(root)
    try:
        with db.kb_conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM ingest_queue").fetchone()[0]
            by_status = conn.execute(
                "SELECT status, COUNT(*) as cnt FROM ingest_queue GROUP BY status"
            ).fetchall()
        return {"success": True, "stats": {"total": total, "by_status": {r["status"]: r["cnt"] for r in by_status}}}
    except Exception as e:
        logger.warning("Failed to fetch queue stats: %s", e)
        return {"success": True, "stats": {"total": 0, "by_status": {}}}


@router.post("/queue/{task_id}/cancel")
async def pipeline_cancel(task_id: str) -> dict:
    return {"success": True}


@router.post("/queue/{task_id}/retry")
async def pipeline_retry(task_id: str) -> dict:
    return {"success": True}


@router.post("/queue/{task_id}/delete")
async def pipeline_delete_task(task_id: str, body: dict) -> dict:
    """Delete a task from the queue stub."""
    return {"success": True}


@router.post("/queue/{task_id}/priority")
async def pipeline_set_priority(task_id: str, body: dict) -> dict:
    """Set task priority stub."""
    return {"success": True}


@router.post("/queue/cleanup")
async def pipeline_cleanup(body: dict) -> dict:
    """Cleanup old completed tasks stub."""
    return {"success": True, "cleaned": 0}


@router.post("/queue/logs")
async def pipeline_logs(body: dict) -> dict:
    """Get ingest logs for a document stub."""
    return {"success": True, "logs": []}
