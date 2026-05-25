"""文档解析器协议.

定义本地解析（PyMuPDF）和远程解析（UniParser API）的统一接口。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ParseOutput:
    """解析器统一输出。"""

    text: str = ""
    markdown: str = ""
    pages: list[str] = field(default_factory=list)
    images: list[Path] = field(default_factory=list)
    tables: list[list[list[str]]] = field(default_factory=list)
    molecules: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def content(self) -> str:
        """优先返回 markdown，否则 text。"""
        return self.markdown or self.text


class BaseDocumentParser(ABC):
    """文档解析器抽象基类。

    本地解析和远程解析均实现此接口，上层只依赖协议。
    """

    @abstractmethod
    def parse(self, pdf_path: Path, **kwargs) -> ParseOutput:
        """解析 PDF 文件，返回统一输出。"""
        ...

    def health(self) -> dict[str, Any]:
        """检查解析器可用性。默认返回 healthy。"""
        return {"status": "healthy"}
