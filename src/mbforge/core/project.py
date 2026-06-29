"""Project lifecycle management — open, scan, file tree."""

from __future__ import annotations

import json
from pathlib import Path

from ..models.project import DocumentEntry, FileNode, ProjectResponse
from ..utils.helpers import ensure_dir, load_json, save_json
from ..utils.logger import get_logger

logger = get_logger("mbforge.project")

MBFORGE_DIR = ".mbforge"
INDEX_FILE = "index.json"


def _mbforge_dir(root: Path) -> Path:
    return root / MBFORGE_DIR


def _index_path(root: Path) -> Path:
    return _mbforge_dir(root) / INDEX_FILE


def open_project(root: str) -> ProjectResponse:
    """Open or create a project at the given root path."""
    p = Path(root)
    if not p.exists():
        p.mkdir(parents=True, exist_ok=True)
    mbf = _mbforge_dir(p)
    ensure_dir(mbf)
    idx = _index_path(p)
    if not idx.exists():
        save_json(idx, [])
    docs = load_json(idx, [])
    name = p.name
    return ProjectResponse(root=str(p), name=name, doc_count=len(docs))


def scan_project_files(root: str) -> list[str]:
    """Scan project directory for supported document files."""
    p = Path(root)
    supported = {".pdf", ".md", ".txt", ".sdf", ".mol", ".mol2", ".pdb", ".smi"}
    skip_dirs = {
        "node_modules", ".venv", "venv", "__pycache__", ".git", "target",
        "dist", "build", ".mypy_cache", ".pytest_cache", ".ruff_cache",
        ".codex", ".claude", "archived", "ref", "tools",
    }
    files: list[str] = []
    for f in p.rglob("*"):
        # Skip heavy/irrelevant directories
        if any(part in skip_dirs or part.startswith(".") for part in f.relative_to(p).parts[:-1]):
            continue
        if f.is_file() and f.suffix.lower() in supported:
            rel = str(f.relative_to(p))
            if not rel.startswith(MBFORGE_DIR) and not rel.startswith("."):
                files.append(rel)
    return sorted(files)


def list_documents(root: str) -> list[DocumentEntry]:
    """List all documents in the project index."""
    idx = _index_path(Path(root))
    data = load_json(idx, [])
    entries: list[DocumentEntry] = []
    for item in data:
        entries.append(
            DocumentEntry(
                doc_id=item.get("doc_id", ""),
                file_path=item.get("file_path", ""),
                file_name=item.get("file_name", Path(item.get("file_path", "")).name),
                doc_type=item.get("doc_type", ""),
                status=item.get("status", "pending"),
                page_count=item.get("page_count", 0),
                created_at=item.get("created_at", ""),
            )
        )
    return entries


def get_file_tree(root: str) -> list[FileNode]:
    """Build a file tree for the project."""
    p = Path(root)
    supported = {".pdf", ".md", ".txt", ".sdf", ".mol", ".mol2", ".pdb", ".smi"}

    def _build(dir_path: Path) -> list[FileNode]:
        nodes: list[FileNode] = []
        try:
            entries = sorted(dir_path.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
        except PermissionError:
            return nodes
        for entry in entries:
            if entry.name.startswith(".") or entry.name == MBFORGE_DIR:
                continue
            rel = str(entry.relative_to(p))
            if entry.is_dir():
                children = _build(entry)
                if children:
                    nodes.append(FileNode(name=entry.name, path=rel, is_dir=True, children=children))
            elif entry.suffix.lower() in supported:
                nodes.append(
                    FileNode(
                        name=entry.name,
                        path=rel,
                        is_dir=False,
                        file_type=entry.suffix.lstrip("."),
                    )
                )
        return nodes

    return _build(p)
