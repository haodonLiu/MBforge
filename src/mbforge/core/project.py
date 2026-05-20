"""项目管理 - Vault 机制.

类似 Obsidian，一个文件夹即一个项目（Vault）。
隐藏目录 `.mbforge/` 存储索引、配置、数据库。
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .settings import ProjectSettings
from ..utils.constants import PROJECT_META_DIR, SUPPORTED_DOC_EXTS, SUPPORTED_MOL_EXTS
from ..utils.helpers import generate_uuid, sha256_file


class DocumentEntry:
    """文件索引条目."""

    def __init__(
        self,
        path: Path,
        doc_id: str = "",
        doc_type: str = "",
        title: str = "",
        indexed: bool = False,
    ):
        self.path = path
        self.doc_id = doc_id or generate_uuid()
        self.doc_type = doc_type or self._detect_type(path)
        self.title = title or path.stem
        self.indexed = indexed
        self.added_at = datetime.now().isoformat()
        self.hash = ""

    @staticmethod
    def _detect_type(path: Path) -> str:
        ext = path.suffix.lower()
        if ext == ".pdf":
            return "pdf"
        if ext == ".md":
            return "markdown"
        if ext in {".sdf", ".mol", ".mol2", ".pdb", ".smi"}:
            return "molecule"
        if ext in {".csv", ".xlsx", ".json"}:
            return "data"
        return "text"

    def to_dict(self) -> Dict:
        return {
            "doc_id": self.doc_id,
            "path": str(self.path.relative_to(self.path.anchor)),
            "doc_type": self.doc_type,
            "title": self.title,
            "indexed": self.indexed,
            "added_at": self.added_at,
            "hash": self.hash,
        }

    @classmethod
    def from_dict(cls, data: Dict, project_root: Path) -> DocumentEntry:
        rel = Path(data["path"])
        # 尝试解析相对路径
        full = project_root / rel
        if not full.exists():
            full = project_root / rel.name
        entry = cls(
            path=full,
            doc_id=data.get("doc_id", ""),
            doc_type=data.get("doc_type", ""),
            title=data.get("title", ""),
            indexed=data.get("indexed", False),
        )
        entry.added_at = data.get("added_at", "")
        entry.hash = data.get("hash", "")
        return entry


class Project:
    """MBForge 项目（Vault）."""

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.meta_dir = self.root / PROJECT_META_DIR
        self.settings = ProjectSettings.load(self.root)
        self._index: Dict[str, DocumentEntry] = {}
        self._load_index()

    @property
    def name(self) -> str:
        return self.settings.name or self.root.name

    def _index_path(self) -> Path:
        return self.meta_dir / "index.json"

    def _load_index(self) -> None:
        path = self._index_path()
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for item in data.get("documents", []):
                    entry = DocumentEntry.from_dict(item, self.root)
                    self._index[entry.doc_id] = entry
            except Exception:
                pass

    def _save_index(self) -> None:
        self.meta_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "version": "0.1.0",
            "updated_at": datetime.now().isoformat(),
            "documents": [e.to_dict() for e in self._index.values()],
        }
        with open(self._index_path(), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    # ---- 目录扫描 ----

    def scan_files(self) -> List[DocumentEntry]:
        """扫描项目目录，更新索引."""
        found_ids = set()
        for file_path in self.root.rglob("*"):
            # 跳过隐藏目录和元数据目录
            if PROJECT_META_DIR in file_path.parts:
                continue
            if file_path.name.startswith("."):
                continue
            if file_path.is_file() and file_path.suffix.lower() in (SUPPORTED_DOC_EXTS | SUPPORTED_MOL_EXTS):
                # 查找或创建条目
                entry = None
                for e in self._index.values():
                    if e.path.resolve() == file_path.resolve():
                        entry = e
                        break
                if entry is None:
                    entry = DocumentEntry(path=file_path)
                    self._index[entry.doc_id] = entry
                # 更新 hash
                try:
                    new_hash = sha256_file(file_path)
                    if new_hash != entry.hash:
                        entry.hash = new_hash
                        entry.indexed = False
                except Exception:
                    pass
                found_ids.add(entry.doc_id)
        # 移除已删除的文件
        to_remove = [k for k in self._index if k not in found_ids]
        for k in to_remove:
            del self._index[k]
        self._save_index()
        return list(self._index.values())

    def get_document(self, doc_id: str) -> Optional[DocumentEntry]:
        return self._index.get(doc_id)

    def get_document_by_path(self, path: Path) -> Optional[DocumentEntry]:
        path = Path(path).resolve()
        for entry in self._index.values():
            if entry.path.resolve() == path:
                return entry
        return None

    def add_file(self, path: Path) -> DocumentEntry:
        """手动添加文件到索引."""
        path = Path(path).resolve()
        existing = self.get_document_by_path(path)
        if existing:
            return existing
        entry = DocumentEntry(path=path)
        try:
            entry.hash = sha256_file(path)
        except Exception:
            pass
        self._index[entry.doc_id] = entry
        self._save_index()
        return entry

    def remove_document(self, doc_id: str) -> None:
        """从索引移除文档（不删除实际文件）."""
        if doc_id in self._index:
            del self._index[doc_id]
            self._save_index()

    def list_documents(self, doc_type: Optional[str] = None) -> List[DocumentEntry]:
        docs = list(self._index.values())
        if doc_type:
            docs = [d for d in docs if d.doc_type == doc_type]
        return docs

    def save_settings(self) -> None:
        self.settings.save(self.root)

    # ---- 静态方法：创建/打开项目 ----

    @classmethod
    def create(cls, root: Path, name: str = "") -> Project:
        """创建新项目."""
        root = Path(root).resolve()
        root.mkdir(parents=True, exist_ok=True)
        meta = root / PROJECT_META_DIR
        meta.mkdir(exist_ok=True)
        # 初始化设置
        settings = ProjectSettings(
            name=name or root.name,
            created_at=datetime.now().isoformat(),
        )
        settings.save(root)
        return cls(root)

    @classmethod
    def open(cls, root: Path) -> Optional[Project]:
        """打开已有项目."""
        root = Path(root).resolve()
        meta = root / PROJECT_META_DIR
        if not meta.exists():
            return None
        return cls(root)

    @classmethod
    def is_valid_project(cls, root: Path) -> bool:
        return (Path(root) / PROJECT_META_DIR).exists()
