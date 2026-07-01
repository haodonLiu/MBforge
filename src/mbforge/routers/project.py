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
from ..models.project import ProjectResponse

router = APIRouter()


@router.get("/common-dirs")
async def common_dirs() -> dict:
    """返回常用目录列表（桌面、文档、下载等）."""
    home = Path.home()
    dirs = []
    # 常用目录
    common = [
        ("Desktop", home / "Desktop"),
        ("Documents", home / "Documents"),
        ("Downloads", home / "Downloads"),
    ]
    for name, path in common:
        if path.exists():
            dirs.append({"name": name, "path": str(path).replace("\\", "/")})
    # 工作区目录（如果存在）
    workspace = home / "Projects"
    if workspace.exists():
        dirs.append({"name": "Projects", "path": str(workspace).replace("\\", "/")})
    return {"dirs": dirs}


@router.post("/open")
async def project_open(body: dict) -> ProjectResponse:
    root = body.get("root", "")
    if not root:
        return ProjectResponse(success=False, root="", name="")
    return open_project(root)


@router.post("/scan")
async def project_scan(body: dict) -> dict:
    root = body.get("root", "")
    recursive = body.get("recursive", False)
    if not root:
        return {"success": False, "documents": [], "warnings": []}
    files = scan_project_files(root, recursive=recursive)
    # 转换为前端期望的 DocumentEntry 格式
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
