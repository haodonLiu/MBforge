"""Common Pydantic response models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class SuccessResponse(BaseModel):
    success: bool = True
    message: str = ""


class ErrorResponse(BaseModel):
    success: bool = False
    error: str
    error_code: str = "internal_error"


class PaginatedResponse(BaseModel):
    items: list[Any]
    total: int
    page: int = 1
    page_size: int = 50


class ModelTestRequest(BaseModel):
    model_id: str
    subpath: str | None = None


class ModelTestResponse(BaseModel):
    success: bool = True
    ok: bool = False
    error: str = ""
    duration_ms: int = 0


class MoleculeRenderRequest(BaseModel):
    smiles: str
    width: int | None = 300
    height: int | None = 200


class MoleculeRenderResponse(BaseModel):
    success: bool = False
    image_base64: str | None = None
    error: str = ""
