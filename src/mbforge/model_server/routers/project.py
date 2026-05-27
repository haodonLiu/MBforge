"""项目路由."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...core.project import Project
from ...utils.constants import PROJECT_META_DIR
from ...utils.exceptions import ProjectNotFoundError, ProjectNotValidError
from ...utils.logger import get_logger
from ..dependencies import get_project_from_root

logger = get_logger(__name__)
router = APIRouter()


class CreateProjectRequest(BaseModel):
    root: str
    name: str = ""


class ProjectResponse(BaseModel):
    name: str
    root: str
    document_count: int
    molecule_count: int
    indexed_count: int


def _project_to_dict(project: Project) -> dict:
    """Format project metadata for API response."""
    docs = project.list_documents()
    return {
        "name": project.name,
        "root": str(project.root),
        "document_count": len(docs),
        "molecule_count": 0,
        "indexed_count": sum(1 for d in docs if d.indexed),
    }


@router.post("/create")
async def create_project(req: CreateProjectRequest) -> dict:
    try:
        project = Project.create(Path(req.root), req.name)
        return {"success": True, "project": _project_to_dict(project)}
    except Exception as e:
        logger.error(f"Failed to create project at {req.root}: {e}", exc_info=True)
        raise ProjectNotFoundError(str(e))


@router.post("/open")
async def open_project(req: CreateProjectRequest) -> dict:
    project = await get_project_from_root(req.root)
    return {"success": True, "project": _project_to_dict(project)}


@router.get("/list")
async def list_documents(root: str) -> dict:
    project = await get_project_from_root(root)
    docs = project.list_documents()
    return {
        "success": True,
        "documents": [
            {
                "doc_id": d.doc_id,
                "path": str(d.path),
                "doc_type": d.doc_type,
                "title": d.title,
                "indexed": d.indexed,
            }
            for d in docs
        ],
    }


@router.post("/scan")
async def scan_project(req: CreateProjectRequest) -> dict:
    project = await get_project_from_root(req.root)
    docs = project.scan_files()
    return {
        "success": True,
        "documents": [
            {
                "doc_id": d.doc_id,
                "path": str(d.path),
                "doc_type": d.doc_type,
                "title": d.title,
                "indexed": d.indexed,
            }
            for d in docs
        ],
    }


def _build_file_tree(root: Path) -> list[dict]:
    """Recursively build a file tree from a directory, excluding hidden and meta dirs."""
    result: list[dict] = []
    try:
        entries = sorted(root.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
    except PermissionError:
        return result

    for entry in entries:
        # Skip hidden files/dirs and .mbforge meta directory
        if entry.name.startswith("."):
            continue
        if entry.name == PROJECT_META_DIR:
            continue
        if entry.is_dir():
            children = _build_file_tree(entry)
            result.append({
                "name": entry.name,
                "path": str(entry),
                "is_dir": True,
                "children": children,
            })
        else:
            result.append({
                "name": entry.name,
                "path": str(entry),
                "is_dir": False,
                "children": [],
            })
    return result


@router.get("/file-tree")
async def file_tree(root: str) -> dict:
    project = await get_project_from_root(root)
    tree = _build_file_tree(project.root)
    return {"success": True, "tree": tree}
