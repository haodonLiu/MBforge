"""Document processing pipeline endpoints."""

from __future__ import annotations

import asyncio
import json
import uuid
from concurrent.futures import Future

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from ..utils.helpers import resolve_root
from ..utils.logger import get_logger

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
        enqueued = await _enqueue_all_unresolved(root)
        return {"success": True, "enqueued": enqueued}

    file_path = body.get("file_path", "")
    if not root or not file_path:
        return {"success": False, "error": "library_root and file_path required"}
    task_id = str(uuid.uuid4())
    doc_id = body.get("doc_id", "")
    future = asyncio.get_running_loop().run_in_executor(
        None, _run_pipeline_sync, file_path, root, doc_id, task_id
    )
    _background_futures[task_id] = future
    future.add_done_callback(lambda f: _background_futures.pop(task_id, None))
    return {"success": True, "task_id": task_id}


async def _enqueue_all_unresolved(root: str) -> int:
    """扫描项目中所有未处理的 PDF 并入队，返回入队数量.

    File scanning and SQLite queue reads/writes run in the shared thread pool
    so they do not block the event loop. Pipeline tasks themselves are still
    launched via ``run_in_executor``.
    """
    from pathlib import Path

    from ..core.database import DatabaseManager
    from ..core.file_scanner import scan_library_files

    db = DatabaseManager.get(root)
    files = await asyncio.to_thread(scan_library_files, root)
    pdf_files = [f for f in files if f.lower().endswith(".pdf")]

    loop = asyncio.get_running_loop()

    def _enqueue_all(conn) -> int:
        count = 0
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
                "INSERT INTO ingest_queue (id, file_path, library_root, status, created_at) VALUES (?, ?, ?, 'pending', datetime('now'))",
                (task_id, full_path, root),
            )
            count += 1
            # 后台运行 pipeline
            future = loop.run_in_executor(
                None, _run_pipeline_sync, full_path, root, "", task_id
            )
            _background_futures[task_id] = future
            future.add_done_callback(lambda f, tid=task_id: _background_futures.pop(tid, None))
        return count

    with db.kb_conn() as conn:
        enqueued = await asyncio.to_thread(_enqueue_all, conn)
    return enqueued


def _run_pipeline_sync(pdf_path: str, library_root: str, doc_id: str, task_id: str):
    try:
        from ..pipeline.runner import run_pipeline

        run_pipeline(
            pdf_path,
            library_root,
            doc_id=doc_id,
            task_id=task_id,
        )
    except Exception as e:
        logger.error("Pipeline failed for %s: %s", pdf_path, e, exc_info=True)
        # Update task status in database
        try:
            from ..core.database import DatabaseManager

            db = DatabaseManager.get(library_root)
            with db.kb_conn() as conn:
                conn.execute(
                    "UPDATE ingest_queue SET status = 'failed', error = ? WHERE id = ?",
                    (str(e), task_id),
                )
        except Exception:
            logger.error("Failed to update task status for %s", task_id)


@router.post("/process")
async def pipeline_process(body: dict) -> dict:
    """Synchronous pipeline execution (blocks until complete)."""
    root = resolve_root(body)
    file_path = body.get("file_path", "")
    doc_id = body.get("doc_id", "")
    if not root or not file_path:
        return {"success": False, "error": "library_root and file_path required"}
    task_id = str(uuid.uuid4())
    try:
        from ..pipeline.runner import run_pipeline

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            lambda: run_pipeline(file_path, root, doc_id=doc_id, task_id=task_id),
        )
        return {
            "success": True,
            "task_id": task_id,
            "doc_id": result.doc_id,
            "page_count": result.page_count,
            "indexed_count": result.indexed_count,
            "parser": result.parser,
            "title": result.title,
            "duration_ms": result.duration_ms,
        }
    except Exception as e:
        logger.error("Pipeline failed: %s", e)
        return {"success": False, "task_id": task_id, "error": str(e)}


@router.post("/queue")
async def pipeline_queue(body: dict) -> dict:
    root = resolve_root(body)
    if not root:
        return {"success": True, "tasks": []}
    from ..core.database import DatabaseManager

    db = DatabaseManager.get(root)

    def _fetch() -> list[dict]:
        with db.kb_conn() as conn:
            rows = conn.execute("SELECT * FROM ingest_queue ORDER BY created_at DESC").fetchall()
            return [dict(r) for r in rows]

    try:
        tasks = await asyncio.to_thread(_fetch)
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
    root = body.get("library_root", "")
    if not root:
        return {"success": True, "stats": {}}
    from ..core.database import DatabaseManager

    db = DatabaseManager.get(root)

    def _fetch() -> dict:
        with db.kb_conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM ingest_queue").fetchone()[0]
            by_status = conn.execute(
                "SELECT status, COUNT(*) as cnt FROM ingest_queue GROUP BY status"
            ).fetchall()
        return {"total": total, "by_status": {r["status"]: r["cnt"] for r in by_status}}

    try:
        stats = await asyncio.to_thread(_fetch)
        return {"success": True, "stats": stats}
    except Exception as e:
        logger.warning("Failed to fetch queue stats: %s", e)
        return {"success": True, "stats": {"total": 0, "by_status": {}}}


@router.get("/events/{task_id}")
async def pipeline_events(
    task_id: str, request: Request, library_root: str
) -> EventSourceResponse:
    """Server-sent events stream for a single pipeline task.

    Reads from the ``ingest_logs`` table and yields one event per log row.
    The connection closes when the task is no longer active and no new rows
    have appeared for a short grace period.
    """
    from ..core.database import DatabaseManager

    async def event_generator():
        last_seen_id = 0
        empty_iterations = 0
        while True:
            if await request.is_disconnected():
                break

            db = DatabaseManager.get(library_root)
            try:
                rows = await asyncio.to_thread(
                    _fetch_logs_since,
                    db,
                    task_id,
                    last_seen_id,
                )
            except Exception as exc:
                logger.warning("Failed to read ingest logs for %s: %s", task_id, exc)
                rows = []

            if rows:
                empty_iterations = 0
                for row in rows:
                    last_seen_id = row["id"]
                    payload = {
                        "stage": row["stage"],
                        "event": row["level"],
                        "message": row["message"],
                        "ts_ms": row["ts_ms"],
                    }
                    if row["data"]:
                        try:
                            payload["data"] = json.loads(row["data"])
                        except Exception:
                            payload["data"] = row["data"]
                    yield {"event": row["level"], "data": json.dumps(payload)}
            else:
                empty_iterations += 1
                if task_id not in _background_futures and empty_iterations > 5:
                    break
                await asyncio.sleep(1)

    return EventSourceResponse(event_generator())


def _fetch_logs_since(db, task_id: str, last_seen_id: int) -> list:
    """Synchronous helper to fetch ingest log rows newer than ``last_seen_id``."""
    with db.kb_conn() as conn:
        return conn.execute(
            """
            SELECT id, stage, level, message, data, ts_ms
            FROM ingest_logs
            WHERE task_id = ? AND id > ?
            ORDER BY id ASC
            """,
            (task_id, last_seen_id),
        ).fetchall()


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
