"""项目管理 - Vault 机制.

类似 Obsidian，一个文件夹即一个项目（Vault）。
隐藏目录 `.mbforge/` 存储索引、配置、数据库。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .settings import ProjectSettings
from ..utils.constants import APP_VERSION, PROJECT_META_DIR, SUPPORTED_DOC_EXTS, SUPPORTED_MOL_EXTS
from ..utils.helpers import generate_uuid, load_json, save_json, sha256_file
from ..utils.logger import get_logger

logger = get_logger(__name__)


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
        self.mtime: float = 0.0

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

    def to_dict(self, project_root: Path | None = None) -> dict:
        resolved = self.path.resolve()
        if project_root is not None:
            try:
                rel_path = str(resolved.relative_to(project_root.resolve()))
            except ValueError:
                rel_path = str(resolved)
        else:
            # fallback: 兼容旧调用方
            try:
                rel_path = str(resolved.relative_to(resolved.anchor))
            except ValueError:
                rel_path = str(resolved)
        return {
            "doc_id": self.doc_id,
            "path": rel_path,
            "doc_type": self.doc_type,
            "title": self.title,
            "indexed": self.indexed,
            "added_at": self.added_at,
            "hash": self.hash,
            "mtime": self.mtime,
        }

    @classmethod
    def from_dict(cls, data: dict, project_root: Path) -> DocumentEntry:
        rel = Path(data["path"])
        # 兼容旧数据：如果 rel 是绝对路径（含盘符或 / 开头），直接用
        if rel.is_absolute():
            full = rel
        else:
            full = project_root / rel
            if not full.exists():
                # fallback: 只用文件名
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
        entry.mtime = data.get("mtime", 0.0)
        return entry


class Project:
    """MBForge 项目（Vault）."""

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.meta_dir = self.root / PROJECT_META_DIR
        self.settings = ProjectSettings.load(self.root)
        self._index: dict[str, DocumentEntry] = {}
        self._path_index: dict[Path, str] = {}  # resolved path -> doc_id
        self._load_index()

    @property
    def name(self) -> str:
        return self.settings.name or self.root.name

    def _index_path(self) -> Path:
        return self.meta_dir / "index.json"

    def _load_index(self) -> None:
        path = self._index_path()
        data = load_json(path)
        if data is not None:
            try:
                for item in data.get("documents", []):
                    entry = DocumentEntry.from_dict(item, self.root)
                    self._index[entry.doc_id] = entry
                    self._path_index[entry.path.resolve()] = entry.doc_id
            except Exception as e:
                logger.warning(f"Failed to load index: {e}")

    def _save_index(self) -> None:
        data = {
            "version": APP_VERSION,
            "updated_at": datetime.now().isoformat(),
            "documents": [e.to_dict(self.root) for e in self._index.values()],
        }
        save_json(self._index_path(), data)

    # ---- 目录扫描 ----

    def scan_files(self) -> list[DocumentEntry]:
        """扫描项目目录，更新索引."""
        found_ids = set()

        for file_path in self.root.rglob("*"):
            # 跳过隐藏目录和元数据目录
            if PROJECT_META_DIR in file_path.parts:
                continue
            if file_path.name.startswith("."):
                continue
            if file_path.is_file() and file_path.suffix.lower() in (
                SUPPORTED_DOC_EXTS | SUPPORTED_MOL_EXTS
            ):
                resolved = file_path.resolve()
                entry = self._index.get(self._path_index.get(resolved))
                is_new = False
                if entry is None:
                    entry = DocumentEntry(path=resolved)
                    self._index[entry.doc_id] = entry
                    self._path_index[resolved] = entry.doc_id
                    is_new = True
                # 仅当 mtime 变化或新文件时才计算 SHA256
                try:
                    mtime = file_path.stat().st_mtime
                    if is_new or mtime != entry.mtime:
                        entry.mtime = mtime
                        entry.hash = sha256_file(file_path)
                        entry.indexed = False
                except Exception as e:
                    logger.debug(f"Stat/hash failed for {file_path}: {e}")
                found_ids.add(entry.doc_id)
        # 移除已删除的文件
        to_remove = [k for k in self._index if k not in found_ids]
        for k in to_remove:
            entry = self._index[k]
            self._path_index.pop(entry.path.resolve(), None)
            del self._index[k]
        self._save_index()
        return list(self._index.values())

    def get_document(self, doc_id: str) -> DocumentEntry | None:
        return self._index.get(doc_id)

    def get_document_by_path(self, path: Path) -> DocumentEntry | None:
        resolved = Path(path).resolve()
        doc_id = self._path_index.get(resolved)
        if doc_id:
            return self._index.get(doc_id)
        return None

    def add_file(self, path: Path) -> DocumentEntry:
        """手动添加文件到索引."""
        path = Path(path).resolve()
        existing = self.get_document_by_path(path)
        if existing:
            return existing
        entry = DocumentEntry(path=path)
        try:
            entry.mtime = path.stat().st_mtime
            entry.hash = sha256_file(path)
        except Exception as e:
            logger.debug(f"Stat/hash failed for {path}: {e}")
        self._index[entry.doc_id] = entry
        self._path_index[path] = entry.doc_id
        self._save_index()
        return entry

    def remove_document(self, doc_id: str) -> None:
        """从索引移除文档（不删除实际文件）."""
        if doc_id in self._index:
            entry = self._index[doc_id]
            resolved = entry.path.resolve()
            self._path_index.pop(resolved, None)
            del self._index[doc_id]
            self._save_index()

    def list_documents(self, doc_type: str | None = None) -> list[DocumentEntry]:
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
    def open(cls, root: Path) -> Project | None:
        """打开已有项目."""
        root = Path(root).resolve()
        meta = root / PROJECT_META_DIR
        if not meta.exists():
            return None
        return cls(root)

    @classmethod
    def is_valid_project(cls, root: Path) -> bool:
        return (Path(root) / PROJECT_META_DIR).exists()
