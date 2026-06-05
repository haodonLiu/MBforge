"""文件操作路由 (Browser dev fallback).

这些端点仅在前端以纯浏览器模式运行时作为降级使用。
文件上传/删除/读取的主路径已在 Rust (Tauri) 中实现。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

from ...utils.exceptions import PathTraversalError
from ...utils.logger import get_logger
from ..dependencies import get_project_from_root

logger = get_logger(__name__)
router = APIRouter()


@router.get("/pdf")
async def serve_pdf(path: str, project_root: str | None = None):
    """Serve a PDF file for preview."""
    try:
        file_path = Path(path)
        if project_root:
            project = await get_project_from_root(project_root)
            root_canon = project.root.resolve()
            path_canon = file_path.resolve()
            if not path_canon.is_relative_to(root_canon):
                raise PathTraversalError(f"Path '{path}' escapes project root")
        if not file_path.exists():
            logger.warning(f"PDF not found: {path}")
            return {"success": False, "error": f"File not found: {path}"}
        if not file_path.suffix.lower() == ".pdf":
            return {"success": False, "error": "Only PDF files can be served"}
        return FileResponse(
            file_path,
            media_type="application/pdf",
            headers={"Cache-Control": "private, max-age=3600"},
        )
    except PathTraversalError:
        raise
    except Exception as e:
        logger.error(f"Serve PDF failed for path={path}: {e}", exc_info=True)
        return {"success": False, "error": f"无法打开 PDF: {e}"}
