"""SQLite database manager — schema creation and connection management.

Two databases per project:
- knowledge_base.db: figure labels, coref predictions, ingest queue, semantic cache
- molecules.db: molecules, images, relations, detections, FTS5 search
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

from ..utils.logger import get_logger

logger = get_logger("mbforge.database")

SCHEMA_VERSION = 3

# 实例缓存：避免重复初始化日志
_db_cache: dict[str, DatabaseManager] = {}

_KB_SCHEMA = """
CREATE TABLE IF NOT EXISTS figure_labels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id TEXT NOT NULL,
    page INTEGER NOT NULL,
    label_bbox TEXT,
    label_text TEXT,
    ocr_conf REAL,
    image_path TEXT,
    UNIQUE(doc_id, page, label_bbox, label_text)
);
CREATE TABLE IF NOT EXISTS coref_predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id TEXT NOT NULL,
    page INTEGER NOT NULL,
    mol_smiles TEXT,
    mol_bbox TEXT,
    mol_conf REAL,
    label_id INTEGER,
    label_text TEXT,
    label_bbox TEXT,
    confidence REAL,
    source TEXT DEFAULT 'geometric',
    is_confirmed INTEGER DEFAULT 0,
    image_path TEXT,
    UNIQUE(doc_id, page, mol_smiles, label_text)
);
CREATE TABLE IF NOT EXISTS ingest_queue (
    id TEXT PRIMARY KEY,
    file_path TEXT NOT NULL,
    doc_id TEXT,
    status TEXT DEFAULT 'pending',
    stage TEXT,
    progress_pct REAL DEFAULT 0,
    pages_total INTEGER DEFAULT 0,
    pages_done INTEGER DEFAULT 0,
    retry_count INTEGER DEFAULT 0,
    error TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS ingest_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id TEXT NOT NULL,
    stage TEXT,
    level TEXT DEFAULT 'info',
    message TEXT,
    ts_ms INTEGER,
    task_id TEXT
);
CREATE TABLE IF NOT EXISTS semantic_cache (
    query_hash TEXT PRIMARY KEY,
    query_text TEXT NOT NULL,
    results TEXT NOT NULL,
    project_root TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    hit_count INTEGER DEFAULT 0,
    last_hit TEXT
);
CREATE INDEX IF NOT EXISTS idx_fl_doc_page ON figure_labels(doc_id, page);
CREATE INDEX IF NOT EXISTS idx_fl_text ON figure_labels(label_text);
CREATE INDEX IF NOT EXISTS idx_cp_doc_page ON coref_predictions(doc_id, page);
CREATE INDEX IF NOT EXISTS idx_cp_text ON coref_predictions(label_text);
CREATE INDEX IF NOT EXISTS idx_cp_smiles ON coref_predictions(mol_smiles);
CREATE INDEX IF NOT EXISTS idx_cp_confirmed ON coref_predictions(is_confirmed);
CREATE INDEX IF NOT EXISTS idx_iq_status ON ingest_queue(status);
CREATE INDEX IF NOT EXISTS idx_il_doc ON ingest_logs(doc_id);
"""

_MOL_SCHEMA = """
CREATE TABLE IF NOT EXISTS molecules (
    mol_id TEXT PRIMARY KEY,
    smiles TEXT NOT NULL,
    esmiles TEXT,
    name TEXT DEFAULT '',
    source_doc TEXT,
    activity REAL,
    activity_type TEXT,
    units TEXT,
    source_type TEXT DEFAULT 'manual',
    status TEXT DEFAULT 'active',
    properties TEXT DEFAULT '{}',
    labels TEXT DEFAULT '[]',
    semantic_tags TEXT DEFAULT '[]',
    notes TEXT DEFAULT '',
    fingerprint BLOB,
    canonical_smiles TEXT,
    review_status TEXT DEFAULT 'pending',
    reviewed_at TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS molecule_images (
    image_id TEXT PRIMARY KEY,
    mol_id TEXT NOT NULL,
    image_path TEXT,
    page INTEGER,
    vlm_esmiles TEXT,
    vlm_confidence REAL,
    is_structure_diagram INTEGER DEFAULT 0,
    bbox_in_image TEXT,
    moldet_conf REAL,
    FOREIGN KEY (mol_id) REFERENCES molecules(mol_id)
);
CREATE TABLE IF NOT EXISTS molecule_relations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mol_a_id TEXT NOT NULL,
    mol_b_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    score REAL,
    metadata TEXT DEFAULT '{}',
    UNIQUE(mol_a_id, mol_b_id, relation_type),
    FOREIGN KEY (mol_a_id) REFERENCES molecules(mol_id),
    FOREIGN KEY (mol_b_id) REFERENCES molecules(mol_id)
);
CREATE TABLE IF NOT EXISTS molecule_detections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mol_id TEXT,
    doc_id TEXT NOT NULL,
    page INTEGER NOT NULL,
    bbox_x0 REAL, bbox_y0 REAL, bbox_x1 REAL, bbox_y1 REAL,
    crop_relpath TEXT,
    conf_moldet REAL,
    conf_molscribe REAL,
    vlm_verified_esmiles TEXT,
    vlm_confidence REAL,
    UNIQUE(mol_id, doc_id, page),
    FOREIGN KEY (mol_id) REFERENCES molecules(mol_id)
);
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS idx_m_smiles ON molecules(smiles);
CREATE INDEX IF NOT EXISTS idx_m_source ON molecules(source_doc);
CREATE INDEX IF NOT EXISTS idx_m_status ON molecules(status);
CREATE INDEX IF NOT EXISTS idx_m_type ON molecules(source_type);
CREATE INDEX IF NOT EXISTS idx_mi_mol ON molecule_images(mol_id);
CREATE INDEX IF NOT EXISTS idx_mr_type ON molecule_relations(relation_type);
CREATE INDEX IF NOT EXISTS idx_md_doc_page ON molecule_detections(doc_id, page);
CREATE INDEX IF NOT EXISTS idx_md_mol ON molecule_detections(mol_id);
"""

_MOL_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS mol_search USING fts5(
    name, notes, smiles, content='molecules', content_rowid='rowid'
);
"""


class DatabaseManager:
    """Manages SQLite connections for a project's two databases."""

    def __init__(self, project_root: str | Path) -> None:
        self._root = Path(project_root)
        self._index_dir = self._root / "index"
        self._index_dir.mkdir(parents=True, exist_ok=True)
        self._kb_path = self._index_dir / "knowledge_base.db"
        self._mol_path = self._index_dir / "molecules.db"
        self._lock = threading.Lock()
        self._initialized = False

    @classmethod
    def get(cls, project_root: str | Path) -> DatabaseManager:
        """获取缓存的实例，避免重复初始化."""
        key = str(Path(project_root).resolve())
        if key not in _db_cache:
            _db_cache[key] = cls(project_root)
        return _db_cache[key]

    def initialize(self) -> None:
        if self._initialized:
            return
        with self._lock:
            if self._initialized:
                return
            self._init_db(self._kb_path, _KB_SCHEMA)
            self._init_db(self._mol_path, _MOL_SCHEMA + _MOL_FTS, versioned=True)
            self._initialized = True
            logger.info("DB initialized: %s", self._index_dir)

    def _init_db(self, path: Path, schema: str, versioned: bool = False) -> None:
        conn = sqlite3.connect(str(path))
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.executescript(schema)
            if versioned:
                existing = conn.execute("SELECT version FROM schema_version").fetchone()
                if existing is None:
                    conn.execute(
                        "INSERT INTO schema_version (version) VALUES (?)",
                        (SCHEMA_VERSION,),
                    )
                elif existing[0] < SCHEMA_VERSION:
                    if existing[0] < 3:
                        self._migrate_molecules_v2_to_v3(conn)
                    conn.execute(
                        "UPDATE schema_version SET version = ?",
                        (SCHEMA_VERSION,),
                    )
            conn.commit()
        finally:
            conn.close()

    @contextmanager
    def kb_conn(self):
        self.initialize()
        conn = sqlite3.connect(str(self._kb_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @contextmanager
    def mol_conn(self):
        self.initialize()
        conn = sqlite3.connect(str(self._mol_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _migrate_molecules_v2_to_v3(self, conn: sqlite3.Connection) -> None:
        existing_cols = {
            r[0]
            for r in conn.execute("SELECT name FROM pragma_table_info('molecules')")
        }
        for column in (
            "canonical_smiles TEXT",
            "review_status TEXT DEFAULT 'pending'",
            "reviewed_at TEXT",
        ):
            col_name = column.split()[0]
            if col_name not in existing_cols:
                conn.execute(f"ALTER TABLE molecules ADD COLUMN {column}")

    @property
    def kb_path(self) -> Path:
        return self._kb_path

    @property
    def mol_path(self) -> Path:
        return self._mol_path
