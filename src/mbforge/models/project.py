"""Project-related Pydantic models."""

from __future__ import annotations

from pydantic import BaseModel


class ProjectResponse(BaseModel):
    success: bool = True
    root: str
    name: str = ""
    doc_count: int = 0


class ScanResponse(BaseModel):
    success: bool = True
    files: list[str] = []
    count: int = 0


class DocumentEntry(BaseModel):
    doc_id: str
    file_path: str
    file_name: str = ""
    doc_type: str = ""
    status: str = "pending"
    page_count: int = 0
    created_at: str = ""


class DocumentEntryWithStatus(DocumentEntry):
    ingest_status: str = ""
    ingest_stage: str = ""
    progress_pct: float = 0.0


class FileNode(BaseModel):
    name: str
    path: str
    is_dir: bool = False
    children: list[FileNode] = []
    doc_id: str | None = None
    file_type: str = ""
