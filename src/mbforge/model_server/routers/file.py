"""文件操作路由."""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ...utils.exceptions import FileAccessError, PathTraversalError
from ...utils.logger import get_logger
from ..dependencies import get_project_from_root

logger = get_logger(__name__)
router = APIRouter()


class DeleteFileRequest(BaseModel):
    project_root: str
    doc_id: str


@router.get("/pdf")
async def serve_pdf(path: str) -> FileResponse:
    """Serve a PDF file for preview."""
    file_path = Path(path)
    if not file_path.exists():
        raise FileAccessError(f"File not found: {path}")
    if not file_path.suffix.lower() == ".pdf":
        raise FileAccessError("Only PDF files can be served")
    return FileResponse(file_path, media_type="application/pdf")


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    project_root: str = Form(...),
) -> dict:
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


@router.post("/delete")
async def delete_file(req: DeleteFileRequest) -> dict:
    project = await get_project_from_root(req.project_root)

    try:
        entry = project.get_document(req.doc_id)
        if entry and entry.path.exists():
            entry.path.unlink()

        project.remove_document(req.doc_id)
        return {"success": True}
    except Exception as e:
        logger.error(f"Failed to delete document {req.doc_id}: {e}", exc_info=True)
        raise FileAccessError(str(e))
