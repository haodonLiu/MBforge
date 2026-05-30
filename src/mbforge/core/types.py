"""Shared type definitions for MBForge.

Replaces the ExtractedContent dataclass previously defined in document.py.
All pipeline code should import from here."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .document_tree import SectionChunk


@dataclass
class ExtractedContent:
    """从文件中提取的结构化内容 (pipeline 版本).

    所有使用此类型的模块应从 `mbforge.core.types` 导入，
    而非直接从 `mbforge.core.document` 导入。
    """

    text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    molecules: list[dict[str, Any]] = field(default_factory=list)
    images: list[Path] = field(default_factory=list)
    tables: list[list[list[str]]] = field(default_factory=list)
    chunks: list[str] = field(default_factory=list)
    summary: str = ""
    headings: list[dict[str, Any]] = field(default_factory=list)
    page_texts: list[str] = field(default_factory=list)
    sections: list[SectionChunk] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "metadata": self.metadata,
            "molecules": self.molecules,
            "images": [str(p) for p in self.images],
            "tables": self.tables,
            "chunks": self.chunks,
            "summary": self.summary,
            "headings": self.headings,
            "sections": [s.__dict__ for s in self.sections],
        }
