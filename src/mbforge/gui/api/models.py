"""Python dataclasses mirroring backend Pydantic models."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MoleculeRecord:
    mol_id: str = ""
    smiles: str = ""
    esmiles: str = ""
    name: str = ""
    activity: float | None = None
    activity_type: str = ""
    units: str = ""
    source_type: str = ""
    status: str = "active"
    notes: str = ""
    labels: list[str] = field(default_factory=list)
    properties: dict = field(default_factory=dict)
    created_at: str = ""


@dataclass
class MoleculeListResponse:
    success: bool = True
    items: list[MoleculeRecord] = field(default_factory=list)
    total: int = 0


@dataclass
class SearchResult:
    text: str = ""
    score: float = 0.0
    doc_id: str = ""
    page: int = 0
    section: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class NoteEntry:
    id: str = ""
    title: str = ""
    content: str = ""
    tags: list[str] = field(default_factory=list)
    links: list[dict] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""


@dataclass
class IngestTask:
    id: str = ""
    file_path: str = ""
    library_root: str = ""
    status: str = "pending"
    stage: str = ""
    progress: float = 0.0
    error: str = ""
    created_at: str = ""


@dataclass
class PipelineStats:
    total: int = 0
    pending: int = 0
    processing: int = 0
    done: int = 0
    failed: int = 0
