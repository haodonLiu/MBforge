"""文档模型与内容管理."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None  # type: ignore

from ..utils.helpers import split_text_chunks


@dataclass
class ExtractedContent:
    """从文件中提取的结构化内容."""

    text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    molecules: list[dict[str, Any]] = field(default_factory=list)
    images: list[Path] = field(default_factory=list)
    tables: list[list[list[str]]] = field(default_factory=list)
    chunks: list[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "metadata": self.metadata,
            "molecules": self.molecules,
            "images": [str(p) for p in self.images],
            "tables": self.tables,
            "chunks": self.chunks,
            "summary": self.summary,
        }


class DocumentProcessor:
    """文档处理器，负责读取和提取各类文件内容."""

    @classmethod
    def read_text(cls, path: Path) -> str:
        """读取纯文本文件."""
        with open(path, encoding="utf-8", errors="ignore") as f:
            return f.read()

    @classmethod
    def read_markdown(cls, path: Path) -> str:
        """读取 Markdown 文件."""
        return cls.read_text(path)

    @classmethod
    def read_pdf_text(cls, path: Path) -> str:
        """使用 PyMuPDF 提取 PDF 文本."""
        text_parts = []
        if fitz is None:
            raise ImportError("PyMuPDF (fitz) is required for PDF processing")
        with fitz.open(str(path)) as doc:
            for page in doc:
                text_parts.append(page.get_text())
        return "\n\n".join(text_parts)

    @classmethod
    def extract_pdf_images(cls, path: Path, output_dir: Path) -> list[Path]:
        """提取 PDF 中的图片."""
        output_dir.mkdir(parents=True, exist_ok=True)
        if fitz is None:
            return []
        images: list[Path] = []
        with fitz.open(str(path)) as doc:
            for page_idx in range(len(doc)):
                page = doc[page_idx]
                img_list = page.get_images(full=True)
                for img_idx, img in enumerate(img_list, start=1):
                    xref = img[0]
                    base_image = doc.extract_image(xref)
                    if base_image:
                        ext = base_image["ext"]
                        img_path = (
                            output_dir / f"page_{page_idx + 1}_img_{img_idx}.{ext}"
                        )
                        with open(img_path, "wb") as f:
                            f.write(base_image["image"])
                        images.append(img_path)
        return images

    @classmethod
    def extract_pdf_tables(cls, path: Path) -> list[list[list[str]]]:
        """简单表格提取（基于文本布局）.

        返回: [表格] -> [行] -> [单元格]
        """
        tables = []
        # TODO: 集成更强大的表格提取
        # 目前返回空，后续可接入 camelot / tabula
        return tables

    @classmethod
    def process(
        cls, path: Path, chunk_size: int = 512, chunk_overlap: int = 128
    ) -> ExtractedContent:
        """处理任意支持的文件，返回结构化内容."""
        path = Path(path)
        ext = path.suffix.lower()

        content = ExtractedContent()
        content.metadata["source"] = str(path)
        content.metadata["filename"] = path.name

        if ext == ".pdf":
            content.text = cls.read_pdf_text(path)
            if fitz:
                content.metadata["pages"] = len(fitz.open(str(path)))
        elif ext == ".md":
            content.text = cls.read_markdown(path)
        elif ext in {".txt", ".json", ".yaml", ".yml"}:
            content.text = cls.read_text(path)
        else:
            content.text = ""

        # 分块
        if content.text:
            content.chunks = split_text_chunks(content.text, chunk_size, chunk_overlap)

        return content
