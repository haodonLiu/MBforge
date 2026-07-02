"""Project management endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter

from ..core.project import (
    get_file_tree,
    list_documents,
    open_project,
    scan_project_files,
)
from ..models.project import (
    ProjectOpenRequest,
    ProjectScanRequest,
    ProjectDocumentsRequest,
    ProjectFileTreeRequest,
    ProjectResponse,
)

router = APIRouter()


@router.get("/common-dirs")
async def common_dirs() -> dict:
    """返回常用目录列表（桌面、文档、下载等）."""
    home = Path.home()
    dirs = []
    common = [
        ("Desktop", home / "Desktop"),
        ("Documents", home / "Documents"),
        ("Downloads", home / "Downloads"),
    ]
    for name, path in common:
        if path.exists():
            dirs.append({"name": name, "path": str(path).replace("\\", "/")})
    workspace = home / "Projects"
    if workspace.exists():
        dirs.append({"name": "Projects", "path": str(workspace).replace("\\", "/")})
    return {"dirs": dirs}


@router.post("/open")
async def project_open(body: ProjectOpenRequest) -> ProjectResponse:
    if not body.root:
        return ProjectResponse(success=False, root="", name="")
    return open_project(body.root)


@router.post("/scan")
async def project_scan(body: ProjectScanRequest) -> dict:
    if not body.root:
        return {"success": False, "documents": [], "warnings": []}
    files = scan_project_files(root=body.root, recursive=body.recursive)
    documents = []
    for f in files:
        doc_type = "pdf" if f.lower().endswith(".pdf") else "markdown"
        documents.append({
            "doc_id": f,
            "path": f,
            "doc_type": doc_type,
            "title": f.rsplit("/", 1)[-1].rsplit("\\", 1)[-1],
            "indexed": False,
        })
    return {"success": True, "documents": documents, "warnings": []}


@router.post("/documents")
async def project_documents(body: ProjectDocumentsRequest) -> dict:
    if not body.root:
        return {"success": False, "documents": []}
    docs = list_documents(body.root)
    return {"success": True, "documents": [d.model_dump() for d in docs]}


@router.post("/file-tree")
async def project_file_tree(body: ProjectFileTreeRequest) -> dict:
    if not body.root:
        return {"success": False, "tree": []}
    tree = get_file_tree(body.root)
    return {"success": True, "tree": [n.model_dump() for n in tree]}
