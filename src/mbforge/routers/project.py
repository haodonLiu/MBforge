"""Project management endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from ..core.project import get_file_tree, list_documents, open_project, scan_project_files
from ..models.project import ProjectResponse, ScanResponse

router = APIRouter()


@router.post("/open")
async def project_open(body: dict) -> ProjectResponse:
    root = body.get("root", "")
    if not root:
        return ProjectResponse(success=False, root="", name="")
    return open_project(root)


@router.post("/scan")
async def project_scan(body: dict) -> ScanResponse:
    root = body.get("root", "")
    if not root:
        return ScanResponse(success=False)
    files = scan_project_files(root)
    return ScanResponse(files=files, count=len(files))


@router.post("/documents")
async def project_documents(body: dict) -> dict:
    root = body.get("root", "")
    if not root:
        return {"success": False, "documents": []}
    docs = list_documents(root)
    return {"success": True, "documents": [d.model_dump() for d in docs]}


@router.post("/file-tree")
async def project_file_tree(body: dict) -> dict:
    root = body.get("root", "")
    if not root:
        return {"success": False, "tree": []}
    tree = get_file_tree(root)
    return {"success": True, "tree": [n.model_dump() for n in tree]}
