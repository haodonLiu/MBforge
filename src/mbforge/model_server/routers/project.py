"""项目路由."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from ...core.project import Project
from ...utils.constants import PROJECT_META_DIR
from ...utils.exceptions import ProjectNotFoundError
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
    try:
        project = await get_project_from_root(req.root)
    except Exception:
        # 目录存在但不是有效项目，自动初始化
        project = Project.create(Path(req.root), req.name or Path(req.root).name)
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


class IndexRequest(BaseModel):
    root: str


@router.post("/index")
async def index_project(req: IndexRequest) -> dict:
    try:
        project = Project.open(Path(req.root))
        if project is None:
            return {"success": False, "error": f"Not a valid project: {req.root}"}

        docs = project.list_documents()
        unindexed = [d for d in docs if not d.indexed and d.doc_type == "pdf"]

        if not unindexed:
            return {"success": True, "indexed": 0, "molecules": 0, "message": "No unindexed PDFs"}

        # Import pipeline components
        from ...parsers.pdf_parser import PDFParserPipeline
        from ...core.knowledge_base import KnowledgeBase
        from ...core.mol_database import MoleculeDatabase
        from ...models import create_embedder_from_config, create_llm_from_config
        from ...utils.config import load_global_config

        config = load_global_config()
        embedder = create_embedder_from_config(config.embed)
        llm = create_llm_from_config(config.llm)
        kb = KnowledgeBase(project.root, embedder=embedder)
        mol_db = MoleculeDatabase(project.root)

        pipeline = PDFParserPipeline(
            llm=llm,
            embedder=embedder,
            knowledge_base=kb,
            mol_db=mol_db,
        )

        indexed_count = 0
        molecule_count = 0

        for doc in unindexed:
            try:
                content = pipeline.parse(
                    doc.path,
                    doc_id=doc.doc_id,
                    extract_molecules=True,
                    summarize=True,
                    index_kb=True,
                )
                doc.indexed = True
                indexed_count += 1
                molecule_count += len(content.molecules)
            except Exception as e:
                logger.error(f"Failed to index {doc.path}: {e}")

        project._save_index()

        return {
            "success": True,
            "indexed": indexed_count,
            "molecules": molecule_count,
            "total_unindexed": len(unindexed),
        }
    except Exception as e:
        logger.error(f"Index project failed: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@router.get("/file-tree")
async def file_tree(root: str) -> dict:
    project = Project.open(Path(root))
    if project is None:
        return {"success": False, "error": f"Not a valid project: {root}"}
    tree = _build_file_tree(project.root)
    return {"success": True, "tree": tree}
