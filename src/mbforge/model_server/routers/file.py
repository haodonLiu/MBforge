"""文件操作路由 (Browser dev fallback).

这些端点仅在前端以纯浏览器模式运行时作为降级使用。
文件上传/删除/读取的主路径已在 Rust (Tauri) 中实现。
"""

from __future__ import annotations
from typing import Any

import shutil
from pathlib import Path

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse

from ...utils.exceptions import FileAccessError, PathTraversalError
from ...utils.logger import get_logger
from ..dependencies import get_project_from_root

logger = get_logger(__name__)
router = APIRouter()


# 支持文本预览的文件扩展名
TEXT_EXTENSIONS = {".md", ".txt", ".csv", ".json", ".yaml", ".yml", ".toml", ".py", ".rs", ".ts", ".tsx", ".js", ".jsx", ".css", ".html"}


@router.get("/content")
async def read_file_content(path: str, project_root: str | None = None):
    """读取文本文件内容（用于 Markdown/TXT 等预览）."""
    try:
        file_path = Path(path)
        if project_root:
            project = await get_project_from_root(project_root)
            root_canon = project.root.resolve()
            path_canon = file_path.resolve()
            if not path_canon.is_relative_to(root_canon):
                raise PathTraversalError(f"Path '{path}' escapes project root")
        if not file_path.exists():
            return {"success": False, "error": f"File not found: {path}"}
        if file_path.suffix.lower() not in TEXT_EXTENSIONS:
            return {"success": False, "error": f"Unsupported file type: {file_path.suffix}"}
        content = file_path.read_text(encoding="utf-8", errors="replace")
        return {"success": True, "content": content, "filename": file_path.name}
    except (PathTraversalError, FileAccessError):
        raise
    except Exception as e:
        logger.error(f"Read file content failed for path={path}: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


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
    except (PathTraversalError, FileAccessError):
        raise
    except Exception as e:
        logger.error(f"Serve PDF failed for path={path}: {e}", exc_info=True)
        return {"success": False, "error": f"无法打开 PDF: {e}"}


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    project_root: str = Form(...),
) -> dict[str, Any]:
    project = await get_project_from_root(project_root)

    # Sanitize filename: strip directory components to prevent path traversal
    safe_name = Path(str(file.filename)).name
    dest = project.root / safe_name

    # Verify resolved path stays within project root
    try:
        if not dest.resolve().is_relative_to(project.root.resolve()):
            raise PathTraversalError(
                f"Uploaded filename '{file.filename}' escapes project root"
            )
    except OSError as e:
        raise FileAccessError(f"Invalid filename: {e}")

    try:
        with open(dest, "wb") as f:
            shutil.copyfileobj(file.file, f)

        entry = project.add_file(dest)
        return {
            "success": True,
            "doc_id": entry.doc_id,
            "path": str(entry.path),
            "doc_type": entry.doc_type,
        }
    except (PathTraversalError, FileAccessError):
        raise
    except Exception as e:
        logger.error(f"Failed to upload file '{safe_name}': {e}", exc_info=True)
        raise FileAccessError(str(e))


