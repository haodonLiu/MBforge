"""项目路由."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from ...core.project import Project

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


@router.post("/create")
async def create_project(req: CreateProjectRequest) -> dict:
    try:
        project = Project.create(Path(req.root), req.name)
        docs = project.list_documents()
        return {
            "success": True,
            "project": {
                "name": project.name,
                "root": str(project.root),
                "document_count": len(docs),
                "molecule_count": 0,
                "indexed_count": sum(1 for d in docs if d.indexed),
            },
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/open")
async def open_project(req: CreateProjectRequest) -> dict:
    try:
        project = Project.open(Path(req.root))
        if project is None:
            return {"success": False, "error": "Not a valid project"}
        docs = project.list_documents()
        return {
            "success": True,
            "project": {
                "name": project.name,
                "root": str(project.root),
                "document_count": len(docs),
                "molecule_count": 0,
                "indexed_count": sum(1 for d in docs if d.indexed),
            },
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/list")
async def list_documents(root: str) -> dict:
    try:
        project = Project.open(Path(root))
        if project is None:
            return {"success": False, "error": "Not a valid project"}
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
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/scan")
async def scan_project(req: CreateProjectRequest) -> dict:
    try:
        project = Project.open(Path(req.root))
        if project is None:
            return {"success": False, "error": "Not a valid project"}
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
    except Exception as e:
        return {"success": False, "error": str(e)}
