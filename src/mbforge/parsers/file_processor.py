"""文件类型分发处理器 — 策略模式.

每种文件类型有独立的处理策略，统一接口：
  extract → index → store

所有类型最终都会写入 RAG 知识库和 output/<doc_id>/ 目录。
"""

from __future__ import annotations

import json
import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Optional

from ..core.document import ExtractedContent
from ..core.todo_manager import TodoEntry
from ..utils.helpers import split_text_chunks
from ..utils.logger import get_logger

logger = get_logger(__name__)


# ---- 策略基类 ----

class FileProcessStrategy(ABC):
    """文件处理策略基类."""

    @abstractmethod
    def extract(self, entry: TodoEntry, source: Path, output_dir: Path) -> ExtractedContent:
        """提取内容."""
        ...

    def index(self, content: ExtractedContent, entry: TodoEntry, **deps) -> None:
        """索引到 RAG 知识库."""
        kb = deps.get("knowledge_base")
        if kb is not None and content.chunks:
            kb.index_document(
                entry.doc_id, content,
                metadata={"source": entry.source_path},
            )

    def store(self, content: ExtractedContent, entry: TodoEntry, output_dir: Path) -> Dict[str, Any]:
        """存储输出文件，返回结果 dict."""
        result: Dict[str, Any] = {"status": "done"}

        # 保存提取内容
        content_path = output_dir / "content.json"
        with open(content_path, "w", encoding="utf-8") as f:
            json.dump(content.to_dict(), f, indent=2, ensure_ascii=False)

        # 保存分块
        if content.chunks:
            chunks_path = output_dir / "chunks.json"
            with open(chunks_path, "w", encoding="utf-8") as f:
                json.dump(content.chunks, f, indent=2, ensure_ascii=False)
            result["chunk_count"] = len(content.chunks)

        result["text_length"] = len(content.text)
        return result


# ---- PDF 策略 ----

class PDFStrategy(FileProcessStrategy):
    """PDF 处理策略：提取 → 分子识别 → 摘要 → 索引."""

    def extract(self, entry, source, output_dir):
        from .pdf_parser import PDFParserPipeline
        pipeline = PDFParserPipeline()  # 组件在 index 阶段注入
        self._pipeline = pipeline
        content = pipeline.parse(
            pdf_path=source,
            doc_id=entry.doc_id,
            extract_molecules=True,
            summarize=True,
            index_kb=False,  # 稍后统一索引
        )
        return content

    def index(self, content, entry, **deps):
        """PDF 索引到 RAG + 分子库."""
        # 索引到知识库
        kb = deps.get("knowledge_base")
        if kb is not None and content.chunks:
            kb.index_document(
                entry.doc_id, content,
                metadata={"source": entry.source_path},
            )

        # 分子入库
        mol_db = deps.get("mol_db")
        if mol_db and content.molecules:
            from ..core.mol_database import MoleculeRecord
            for m in content.molecules:
                mol_db.add_molecule(MoleculeRecord(
                    smiles=m.get("smiles", ""),
                    name=m.get("name", ""),
                    source_doc=entry.doc_id,
                ))

    def store(self, content, entry, output_dir):
        result = super().store(content, entry, output_dir)

        if content.summary:
            summary_path = output_dir / "summary.json"
            with open(summary_path, "w", encoding="utf-8") as f:
                json.dump({"summary": content.summary}, f, indent=2, ensure_ascii=False)
            result["has_summary"] = True

        if content.molecules:
            molecules_path = output_dir / "molecules.json"
            with open(molecules_path, "w", encoding="utf-8") as f:
                json.dump(content.molecules, f, indent=2, ensure_ascii=False)
            result["molecule_count"] = len(content.molecules)

        return result


# ---- Markdown 策略 ----

class MarkdownStrategy(FileProcessStrategy):
    """Markdown 策略：直接读取 → 分块 → 索引."""

    def extract(self, entry, source, output_dir):
        text = source.read_text(encoding="utf-8")
        chunks = split_text_chunks(text)
        return ExtractedContent(
            text=text,
            chunks=chunks,
            metadata={"source": str(source)},
        )


# ---- 纯文本策略 ----

class TextStrategy(FileProcessStrategy):
    """纯文本策略：读取 → 分块 → 索引."""

    def extract(self, entry, source, output_dir):
        text = source.read_text(encoding="utf-8", errors="replace")
        chunks = split_text_chunks(text)
        return ExtractedContent(
            text=text,
            chunks=chunks,
            metadata={"source": str(source)},
        )


# ---- 分子文件策略 ----

class MoleculeStrategy(FileProcessStrategy):
    """分子文件策略（SDF/MOL/MOL2/PDB/SMI）：解析分子 → 入分子库."""

    def extract(self, entry, source, output_dir):
        ext = source.suffix.lower()
        molecules = []

        if ext == ".smi":
            lines = source.read_text(encoding="utf-8").strip().split("\n")
            for line in lines:
                line = line.strip()
                if line and not line.startswith("#"):
                    parts = line.split()
                    molecules.append({
                        "smiles": parts[0],
                        "name": parts[1] if len(parts) > 1 else "",
                    })
        else:
            try:
                from rdkit import Chem
                if ext == ".sdf":
                    supplier = Chem.SDMolSupplier(str(source))
                elif ext == ".mol":
                    mol = Chem.MolFromMolFile(str(source))
                    supplier = [mol] if mol else []
                elif ext == ".pdb":
                    mol = Chem.MolFromPDBFile(str(source))
                    supplier = [mol] if mol else []
                else:
                    supplier = []

                for mol in supplier:
                    if mol is not None:
                        Chem.SanitizeMol(mol)
                        molecules.append({
                            "smiles": Chem.MolToSmiles(mol),
                            "name": mol.GetProp("_Name") if mol.HasProp("_Name") else "",
                        })
            except Exception as e:
                logger.warning(f"RDKit parsing failed for {source}: {e}")
                shutil.copy2(source, output_dir / source.name)

        # 分子文件的 text 是分子列表的文本表示
        text = "\n".join(f"{m.get('name', '')}: {m['smiles']}" for m in molecules)
        return ExtractedContent(
            text=text,
            molecules=molecules,
            metadata={"source": str(source), "molecule_count": len(molecules)},
        )

    def index(self, content, entry, **deps):
        """分子入分子库 + 文本描述入 RAG."""
        mol_db = deps.get("mol_db")
        if mol_db and content.molecules:
            from ..core.mol_database import MoleculeRecord
            for m in content.molecules:
                mol_db.add_molecule(MoleculeRecord(
                    smiles=m["smiles"],
                    name=m.get("name", ""),
                    source_doc=entry.doc_id,
                ))

        # 分子描述也入 RAG
        super().index(content, entry, **deps)

    def store(self, content, entry, output_dir):
        result = super().store(content, entry, output_dir)
        if content.molecules:
            molecules_path = output_dir / "molecules.json"
            with open(molecules_path, "w", encoding="utf-8") as f:
                json.dump(content.molecules, f, indent=2, ensure_ascii=False)
            result["molecule_count"] = len(content.molecules)
        return result


# ---- 数据表策略 ----

class DataTableStrategy(FileProcessStrategy):
    """数据表策略（CSV/XLSX）：读取 → 转 JSON → 索引."""

    def extract(self, entry, source, output_dir):
        import pandas as pd

        ext = source.suffix.lower()
        if ext == ".csv":
            df = pd.read_csv(source)
        else:
            df = pd.read_excel(source)

        # 把表格转为可索引的文本
        text = f"表格: {source.name}\n列: {', '.join(df.columns)}\n行数: {len(df)}\n\n"
        text += df.head(100).to_string(index=False)

        chunks = split_text_chunks(text)
        self._df_columns = list(df.columns)
        self._df_shape = list(df.shape)
        self._df_head = df.head(1000).to_dict(orient="records")

        return ExtractedContent(
            text=text,
            chunks=chunks,
            metadata={"source": str(source), "columns": list(df.columns), "rows": len(df)},
        )

    def store(self, content, entry, output_dir):
        result = super().store(content, entry, output_dir)

        # 额外保存结构化数据
        data = {
            "columns": self._df_columns,
            "shape": self._df_shape,
            "data": self._df_head,
        }
        data_path = output_dir / "data.json"
        with open(data_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)

        # 复制原始文件
        source = output_dir.parent.parent / entry.source_path
        if source.exists():
            shutil.copy2(source, output_dir / source.name)

        result["columns"] = self._df_columns
        result["row_count"] = self._df_shape[0]
        return result


# ---- JSON 策略 ----

class JsonStrategy(FileProcessStrategy):
    """JSON 策略：读取 → 转文本索引."""

    def extract(self, entry, source, output_dir):
        data = json.loads(source.read_text(encoding="utf-8"))
        text = json.dumps(data, indent=2, ensure_ascii=False)
        if len(text) > 20000:
            text = text[:20000] + "\n... (truncated)"
        chunks = split_text_chunks(text)
        return ExtractedContent(
            text=text,
            chunks=chunks,
            metadata={"source": str(source), "keys": list(data.keys()) if isinstance(data, dict) else "array"},
        )

    def store(self, content, entry, output_dir):
        result = super().store(content, entry, output_dir)
        shutil.copy2(output_dir.parent.parent / entry.source_path, output_dir / "content.json")
        return result


# ---- 策略注册表 ----

STRATEGIES: Dict[str, FileProcessStrategy] = {
    ".pdf": PDFStrategy(),
    ".md": MarkdownStrategy(),
    ".txt": TextStrategy(),
    ".sdf": MoleculeStrategy(),
    ".mol": MoleculeStrategy(),
    ".mol2": MoleculeStrategy(),
    ".pdb": MoleculeStrategy(),
    ".smi": MoleculeStrategy(),
    ".csv": DataTableStrategy(),
    ".xlsx": DataTableStrategy(),
    ".json": JsonStrategy(),
}


def get_strategy(ext: str) -> FileProcessStrategy:
    """按扩展名获取处理策略."""
    return STRATEGIES.get(ext, TextStrategy())


# ---- 统一入口 ----

def process_file(
    entry: TodoEntry,
    source_path: Path,
    output_dir: Path,
    llm=None,
    embedder=None,
    vlm=None,
    knowledge_base=None,
    mol_db=None,
) -> Dict[str, Any]:
    """处理单个文件：extract → index → store.

    Returns:
        处理结果 dict，写入 output/<doc_id>/index.json
    """
    ext = source_path.suffix.lower()
    strategy = get_strategy(ext)

    deps = {
        "llm": llm,
        "embedder": embedder,
        "vlm": vlm,
        "knowledge_base": knowledge_base,
        "mol_db": mol_db,
    }

    # 1. 提取
    content = strategy.extract(entry, source_path, output_dir)

    # 2. 索引到 RAG
    strategy.index(content, entry, **deps)

    # 3. 存储输出
    result = strategy.store(content, entry, output_dir)

    # 元信息
    result["filename"] = entry.filename
    result["doc_id"] = entry.doc_id
    result["source_path"] = entry.source_path
    result["file_type"] = ext
    result["strategy"] = type(strategy).__name__
    result["rag_indexed"] = knowledge_base is not None and bool(content.chunks)

    return result
