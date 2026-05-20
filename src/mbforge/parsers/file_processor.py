"""文件类型分发处理器.

根据文件扩展名分发到对应的 parser，输出存入 output/<doc_id>/ 目录。
"""

from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from ..core.document import DocumentProcessor
from ..core.todo_manager import TodoEntry
from ..utils.helpers import generate_uuid, split_text_chunks
from ..utils.logger import get_logger

logger = get_logger(__name__)


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
    """根据文件类型分发处理.

    Returns:
        处理结果 dict，写入 output/<doc_id>/index.json
    """
    ext = source_path.suffix.lower()

    processors = {
        ".pdf": _process_pdf,
        ".md": _process_markdown,
        ".txt": _process_text,
        ".sdf": _process_molecule,
        ".mol": _process_molecule,
        ".mol2": _process_molecule,
        ".pdb": _process_molecule,
        ".smi": _process_molecule,
        ".csv": _process_data_table,
        ".xlsx": _process_data_table,
        ".json": _process_json,
    }

    processor = processors.get(ext)
    if processor is None:
        # 未知类型，按文本处理
        processor = _process_text

    result = processor(entry, source_path, output_dir, llm=llm, embedder=embedder,
                       vlm=vlm, knowledge_base=knowledge_base, mol_db=mol_db)
    result["filename"] = entry.filename
    result["doc_id"] = entry.doc_id
    result["source_path"] = entry.source_path
    result["file_type"] = ext
    return result


def _process_pdf(
    entry: TodoEntry,
    source_path: Path,
    output_dir: Path,
    **kwargs,
) -> Dict[str, Any]:
    """处理 PDF 文件."""
    from .pdf_parser import PDFParserPipeline

    pipeline = PDFParserPipeline(
        llm=kwargs.get("llm"),
        embedder=kwargs.get("embedder"),
        vlm=kwargs.get("vlm"),
        knowledge_base=kwargs.get("knowledge_base"),
        mol_db=kwargs.get("mol_db"),
    )
    content = pipeline.parse(
        pdf_path=source_path,
        doc_id=entry.doc_id,
        extract_molecules=True,
        summarize=True,
        index_kb=kwargs.get("knowledge_base") is not None,
    )

    # 保存提取内容
    content_path = output_dir / "content.json"
    with open(content_path, "w", encoding="utf-8") as f:
        json.dump(content.to_dict(), f, indent=2, ensure_ascii=False)

    # 保存摘要
    if content.summary:
        summary_path = output_dir / "summary.json"
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump({"summary": content.summary}, f, indent=2, ensure_ascii=False)

    # 保存分子数据
    if content.molecules:
        molecules_path = output_dir / "molecules.json"
        with open(molecules_path, "w", encoding="utf-8") as f:
            json.dump(content.molecules, f, indent=2, ensure_ascii=False)

    # 保存分块
    if content.chunks:
        chunks_path = output_dir / "chunks.json"
        with open(chunks_path, "w", encoding="utf-8") as f:
            json.dump(content.chunks, f, indent=2, ensure_ascii=False)

    return {
        "status": "done",
        "text_length": len(content.text),
        "chunk_count": len(content.chunks),
        "molecule_count": len(content.molecules),
        "has_summary": bool(content.summary),
    }


def _process_markdown(
    entry: TodoEntry,
    source_path: Path,
    output_dir: Path,
    **kwargs,
) -> Dict[str, Any]:
    """处理 Markdown 文件."""
    text = source_path.read_text(encoding="utf-8")
    chunks = split_text_chunks(text)

    content_data = {
        "text": text,
        "chunks": chunks,
        "metadata": {"source": str(source_path)},
    }

    content_path = output_dir / "content.json"
    with open(content_path, "w", encoding="utf-8") as f:
        json.dump(content_data, f, indent=2, ensure_ascii=False)

    chunks_path = output_dir / "chunks.json"
    with open(chunks_path, "w", encoding="utf-8") as f:
        json.dump(chunks, f, indent=2, ensure_ascii=False)

    # 索引到知识库
    kb = kwargs.get("knowledge_base")
    if kb is not None:
        from ..core.document import ExtractedContent
        content = ExtractedContent(text=text, chunks=chunks)
        kb.index_document(entry.doc_id, content, metadata={"source": str(source_path)})

    return {
        "status": "done",
        "text_length": len(text),
        "chunk_count": len(chunks),
    }


def _process_text(
    entry: TodoEntry,
    source_path: Path,
    output_dir: Path,
    **kwargs,
) -> Dict[str, Any]:
    """处理纯文本文件."""
    text = source_path.read_text(encoding="utf-8", errors="replace")
    chunks = split_text_chunks(text)

    content_data = {
        "text": text,
        "chunks": chunks,
        "metadata": {"source": str(source_path)},
    }

    content_path = output_dir / "content.json"
    with open(content_path, "w", encoding="utf-8") as f:
        json.dump(content_data, f, indent=2, ensure_ascii=False)

    return {
        "status": "done",
        "text_length": len(text),
        "chunk_count": len(chunks),
    }


def _process_molecule(
    entry: TodoEntry,
    source_path: Path,
    output_dir: Path,
    **kwargs,
) -> Dict[str, Any]:
    """处理分子文件（SDF/MOL/MOL2/PDB/SMI）."""
    ext = source_path.suffix.lower()
    molecules = []

    if ext == ".smi":
        # SMILES 文件：每行一个 SMILES
        lines = source_path.read_text(encoding="utf-8").strip().split("\n")
        for line in lines:
            line = line.strip()
            if line and not line.startswith("#"):
                parts = line.split()
                molecules.append({
                    "smiles": parts[0],
                    "name": parts[1] if len(parts) > 1 else "",
                })
    else:
        # SDF/MOL/MOL2/PDB：尝试用 RDKit 读取
        try:
            from rdkit import Chem
            supplier_path = str(source_path)
            if ext == ".sdf":
                supplier = Chem.SDMolSupplier(supplier_path)
            elif ext == ".mol":
                mol = Chem.MolFromMolFile(supplier_path)
                supplier = [mol] if mol else []
            elif ext == ".pdb":
                mol = Chem.MolFromPDBFile(supplier_path)
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
            logger.warning(f"RDKit parsing failed for {source_path}: {e}")
            # 回退：复制原始文件
            shutil.copy2(source_path, output_dir / source_path.name)

    # 保存分子数据
    if molecules:
        molecules_path = output_dir / "molecules.json"
        with open(molecules_path, "w", encoding="utf-8") as f:
            json.dump(molecules, f, indent=2, ensure_ascii=False)

    # 入分子数据库
    mol_db = kwargs.get("mol_db")
    if mol_db and molecules:
        from ..core.mol_database import MoleculeRecord
        for m in molecules:
            rec = MoleculeRecord(
                smiles=m["smiles"],
                name=m.get("name", ""),
                source_doc=entry.doc_id,
            )
            mol_db.add_molecule(rec)

    return {
        "status": "done",
        "molecule_count": len(molecules),
    }


def _process_data_table(
    entry: TodoEntry,
    source_path: Path,
    output_dir: Path,
    **kwargs,
) -> Dict[str, Any]:
    """处理数据表文件（CSV/XLSX）."""
    import pandas as pd

    ext = source_path.suffix.lower()
    if ext == ".csv":
        df = pd.read_csv(source_path)
    else:
        df = pd.read_excel(source_path)

    # 保存为 JSON
    data = {
        "columns": list(df.columns),
        "shape": list(df.shape),
        "data": df.head(1000).to_dict(orient="records"),  # 限制行数
    }

    data_path = output_dir / "data.json"
    with open(data_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)

    # 也复制原始文件
    shutil.copy2(source_path, output_dir / source_path.name)

    return {
        "status": "done",
        "columns": list(df.columns),
        "row_count": len(df),
    }


def _process_json(
    entry: TodoEntry,
    source_path: Path,
    output_dir: Path,
    **kwargs,
) -> Dict[str, Any]:
    """处理 JSON 文件."""
    data = json.loads(source_path.read_text(encoding="utf-8"))

    content_path = output_dir / "content.json"
    shutil.copy2(source_path, content_path)

    return {
        "status": "done",
        "keys": list(data.keys()) if isinstance(data, dict) else "array",
    }
