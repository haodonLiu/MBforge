"""文件操作路由."""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, File, Form, UploadFile
from pydantic import BaseModel

from ...core.project import Project

router = APIRouter()


class DeleteFileRequest(BaseModel):
    project_root: str
    doc_id: str


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    project_root: str = Form(...),
) -> dict:
    try:
        project = Project.open(Path(project_root))
        if project is None:
            return {"success": False, "error": "Not a valid project"}

        dest = project.root / file.filename
        with open(dest, "wb") as f:
            shutil.copyfileobj(file.file, f)

        entry = project.add_file(dest)
        return {
            "success": True,
            "doc_id": entry.doc_id,
            "path": str(entry.path),
            "doc_type": entry.doc_type,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/delete")
async def delete_file(req: DeleteFileRequest) -> dict:
    try:
        project = Project.open(Path(req.project_root))
        if project is None:
            return {"success": False, "error": "Not a valid project"}

        entry = project.get_document(req.doc_id)
        if entry and entry.path.exists():
            entry.path.unlink()

        project.remove_document(req.doc_id)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}
