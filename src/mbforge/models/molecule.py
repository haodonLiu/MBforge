"""Molecule-related Pydantic models."""

from __future__ import annotations

from pydantic import BaseModel, Field


# ---- Request models ----

class MoleculeListRequest(BaseModel):
    project_root: str = Field(..., description="Project root directory")
    page: int = Field(1, ge=1, description="Page number")
    page_size: int = Field(50, ge=1, le=200, description="Items per page")
    status: str = Field("", description="Filter by status")


class MoleculeSearchRequest(BaseModel):
    project_root: str = Field(..., description="Project root directory")
    query: str = Field(..., description="Search query")
    top_k: int = Field(20, ge=1, le=100, description="Max results")


class MoleculeGetRequest(BaseModel):
    project_root: str = Field(..., description="Project root directory")
    mol_id: str = Field(..., description="Molecule ID")


class MoleculeCreateRequest(BaseModel):
    project_root: str = Field(..., description="Project root directory")
    smiles: str = Field(..., description="SMILES string")
    mol_id: str | None = Field(None, description="Molecule ID (auto-generated if omitted)")
    esmiles: str = Field("", description="Extended SMILES")
    name: str = Field("", description="Molecule name")
    source_type: str = Field("manual", description="Source type")


class MoleculeUpdateRequest(BaseModel):
    project_root: str = Field(..., description="Project root directory")
    name: str | None = None
    esmiles: str | None = None
    activity: float | None = None
    activity_type: str | None = None
    units: str | None = None
    status: str | None = None
    notes: str | None = None
    labels: list[str] | None = None
    properties: dict | None = None


class MoleculeDeleteRequest(BaseModel):
    project_root: str = Field(..., description="Project root directory")


class MoleculeStatsRequest(BaseModel):
    project_root: str = Field(..., description="Project root directory")


# ---- Response models ----

class MoleculeListResponse(BaseModel):
    success: bool = True
    items: list[dict] = []
    total: int = 0


class MoleculeGetResponse(BaseModel):
    success: bool = True
    molecule: dict | None = None


class MoleculeCreateResponse(BaseModel):
    success: bool = True
    mol_id: str = ""


class MoleculeStatsResponse(BaseModel):
    success: bool = True
    total: int = 0
    by_status: dict[str, int] = {}
    by_source: dict[str, int] = {}
