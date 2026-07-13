"""SQLite database manager — schema creation and connection management.

Two databases per project:
- knowledge_base.db: figure labels, coref predictions, ingest queue, semantic cache
- molecules.db: molecules, images, relations, detections, evidence, FTS5 search
"""

from __future__ import annotations

import functools
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from ..utils.logger import get_logger

logger = get_logger("mbforge.database")

SCHEMA_VERSION = 5

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
    task_id TEXT,
    data TEXT
);
CREATE TABLE IF NOT EXISTS semantic_cache (
    query_hash TEXT PRIMARY KEY,
    query_text TEXT NOT NULL,
    results TEXT NOT NULL,
    library_root TEXT,
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
CREATE TABLE IF NOT EXISTS sections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id TEXT NOT NULL,
    section_index INTEGER NOT NULL,
    title TEXT,
    level INTEGER DEFAULT 1,
    char_start INTEGER,
    char_end INTEGER,
    page_start INTEGER,
    page_end INTEGER,
    paragraph_count INTEGER DEFAULT 0,
    molecule_count INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_sec_doc ON sections(doc_id, section_index);
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
CREATE TABLE IF NOT EXISTS text_molecule_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id TEXT NOT NULL,
    mol_id TEXT NOT NULL,
    section_index INTEGER,
    page INTEGER,
    text_excerpt TEXT,
    role TEXT DEFAULT 'mentioned',
    code_text TEXT,
    char_start INTEGER,
    char_end INTEGER,
    created_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_m_smiles ON molecules(smiles);
CREATE INDEX IF NOT EXISTS idx_m_source ON molecules(source_doc);
CREATE INDEX IF NOT EXISTS idx_m_status ON molecules(status);
CREATE INDEX IF NOT EXISTS idx_m_type ON molecules(source_type);
CREATE INDEX IF NOT EXISTS idx_m_canonical ON molecules(canonical_smiles);
CREATE INDEX IF NOT EXISTS idx_mi_mol ON molecule_images(mol_id);
CREATE INDEX IF NOT EXISTS idx_mr_type ON molecule_relations(relation_type);
CREATE INDEX IF NOT EXISTS idx_tml_doc_mol ON text_molecule_links(doc_id, mol_id);
CREATE INDEX IF NOT EXISTS idx_md_doc_page ON molecule_detections(doc_id, page);
CREATE INDEX IF NOT EXISTS idx_md_mol ON molecule_detections(mol_id);
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);
"""

# First-class evidence chain: every (molecule, document, page) combination where
# the molecule was observed — figure kind (with bbox + crop), text kind (with
# context excerpt + MoleCode block), or future table kind.
#
# `canonical_smiles` is the natural join key into `molecules.canonical_smiles`.
# We do NOT add a FOREIGN KEY because the pipeline writes evidence rows first
# (during detect / register) and only the admin router creates `molecules`
# rows on demand. Adding a FK would block the detect path. The join is
# enforced by application logic in routers/molecule.py.
_EVIDENCE_SCHEMA = """
CREATE TABLE IF NOT EXISTS evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_smiles TEXT NOT NULL,
    mol_id TEXT,
    doc_id TEXT NOT NULL,
    page INTEGER,
    bbox_x0 REAL, bbox_y0 REAL, bbox_x1 REAL, bbox_y1 REAL,
    crop_relpath TEXT,
    context_text TEXT,
    code_text TEXT,
    role TEXT DEFAULT 'detected',
    kind TEXT NOT NULL,
    confidence REAL,
    source_type TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    -- Phase 1 (2026-07-10): row-alignment metadata (NULL for pre-migration rows)
    row_label TEXT,
    table_idx INTEGER,
    row_idx INTEGER,
    col_idx INTEGER
);
CREATE INDEX IF NOT EXISTS idx_ev_cs ON evidence(canonical_smiles);
CREATE INDEX IF NOT EXISTS idx_ev_doc_page ON evidence(doc_id, page);
CREATE INDEX IF NOT EXISTS idx_ev_kind ON evidence(kind);
"""

_MOL_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS mol_search USING fts5(
    name, notes, smiles, content='molecules', content_rowid='rowid'
);
"""


class DatabaseManager:
    """Manages SQLite connections for a project's two databases."""

    def __init__(self, library_root: str | Path) -> None:
        from .layout import LibraryLayout

        self._root = Path(library_root)
        # Phase 4+: unified single database under {root}/.mbforge/library.db.
        # The legacy {root}/index/*.db layout is migrated by
        # `mbforge.migrate-library`; new code should call
        # LibraryLayout(library_root).database_path directly.
        self._layout = LibraryLayout(library_root)
        self._layout.ensure_metadata_dir()
        self._db_path = self._layout.database_path
        self._kb_path = self._db_path
        self._mol_path = self._db_path
        self._lock = threading.Lock()
        # threading.Event gives a clearer double-checked-locking pattern than
        # a plain bool and avoids the (theoretical) re-ordering issues of a
        # naked flag across threads.
        self._initialized = threading.Event()
        # Single shared physical connection for the unified layout. Refcounted
        # so ``kb_conn()`` and ``mol_conn()`` do not open redundant connections
        # to the same file. Callers do not nest these context managers, so
        # simple refcounting is sufficient.
        self._shared_conn: sqlite3.Connection | None = None
        self._shared_refcount = 0

    @staticmethod
    def molecule_schema() -> str:
        """Return SQL for molecule tables + evidence + FTS5 index."""
        return _MOL_SCHEMA + _EVIDENCE_SCHEMA + _MOL_FTS

    @classmethod
    @functools.lru_cache(maxsize=128)
    def get(cls, library_root: str | Path) -> DatabaseManager:
        """Return a cached instance keyed by resolved absolute path."""
        return cls(library_root)

    def initialize(self) -> None:
        if self._initialized.is_set():
            return
        with self._lock:
            if self._initialized.is_set():
                return
            self._init_db(self._kb_path, _KB_SCHEMA)
            self._init_db(
                self._mol_path,
                _MOL_SCHEMA + _EVIDENCE_SCHEMA + _MOL_FTS,
                versioned=True,
            )
            self._initialized.set()
            logger.info("DB initialized: %s", self._db_path)

    def _init_db(self, path: Path, schema: str, versioned: bool = False) -> None:
        conn = sqlite3.connect(str(path))
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.executescript(schema)
            if versioned:
                existing = conn.execute("SELECT version FROM schema_version").fetchone()
                if existing is None:
                    # Greenfield — current schema is already at SCHEMA_VERSION.
                    conn.execute(
                        "INSERT INTO schema_version (version) VALUES (?)",
                        (SCHEMA_VERSION,),
                    )
                elif existing[0] < SCHEMA_VERSION:
                    if existing[0] < 3:
                        self._migrate_molecules_v2_to_v3(conn)
                    if existing[0] < 4:
                        self._migrate_molecules_v3_to_v4(conn)
                    if existing[0] < 5:
                        self._migrate_molecules_v4_to_v5(conn)
                    conn.execute(
                        "UPDATE schema_version SET version = ?",
                        (SCHEMA_VERSION,),
                    )
            else:
                self._migrate_kb_columns(conn)
            conn.commit()
        finally:
            conn.close()

    def _migrate_kb_columns(self, conn: sqlite3.Connection) -> None:
        """Idempotent KB schema migrations for unversioned databases.

        Adds columns introduced after the initial KB schema was deployed.
        """
        existing_cols = {
            r[0]
            for r in conn.execute("SELECT name FROM pragma_table_info('ingest_logs')")
        }
        if "data" not in existing_cols:
            conn.execute("ALTER TABLE ingest_logs ADD COLUMN data TEXT")

    @contextmanager
    def _shared_connection(self) -> Iterator[sqlite3.Connection]:
        """Yield the single shared connection for the unified database.

        Refcounted so sequential ``kb_conn()`` / ``mol_conn()`` calls reuse
        the same physical SQLite connection instead of opening two separate
        ones to ``{root}/.mbforge/library.db``.
        """
        with self._lock:
            if self._shared_conn is None:
                self._shared_conn = sqlite3.connect(str(self._db_path))
                self._shared_conn.row_factory = sqlite3.Row
                self._shared_conn.execute("PRAGMA foreign_keys=ON")
            self._shared_refcount += 1
            conn = self._shared_conn
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            with self._lock:
                self._shared_refcount -= 1
                if self._shared_refcount <= 0:
                    self._shared_conn.close()
                    self._shared_conn = None

    @contextmanager
    def kb_conn(self):
        self.initialize()
        if self._kb_path == self._mol_path:
            with self._shared_connection() as conn:
                yield conn
            return
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
        if self._kb_path == self._mol_path:
            with self._shared_connection() as conn:
                yield conn
            return
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

    @contextmanager
    def transaction(self):
        """Best-effort transaction across both project databases.

        Yields a tuple ``(kb_conn, mol_conn)``. If either connection raises an
        exception, both are rolled back. This prevents the pipeline from leaving
        orphan records in one database when a later write to the other fails.

        In the unified single-DB layout (Phase 4+), ``kb_conn`` and
        ``mol_conn`` are the same physical connection to avoid SQLite locking
        the file against itself.

        Note: SQLite does not support true two-phase commit across separate
        database files, so this is best-effort within a single process. It is
        sufficient for Phase 0 pipeline consistency.
        """
        self.initialize()
        unified = self._kb_path == self._mol_path
        if unified:
            with self._shared_connection() as kb_conn:
                yield kb_conn, kb_conn
            return
        kb_conn = sqlite3.connect(str(self._kb_path))
        kb_conn.row_factory = sqlite3.Row
        kb_conn.execute("PRAGMA foreign_keys=ON")
        mol_conn = sqlite3.connect(str(self._mol_path))
        mol_conn.row_factory = sqlite3.Row
        mol_conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield kb_conn, mol_conn
            kb_conn.commit()
            mol_conn.commit()
        except Exception:
            kb_conn.rollback()
            mol_conn.rollback()
            raise
        finally:
            kb_conn.close()
            mol_conn.close()

    def execute(
        self,
        sql: str,
        parameters: tuple | list | dict | None = None,
        *,
        db: str = "kb",
    ) -> list[sqlite3.Row]:
        """Execute a single statement and return all rows.

        Convenience helper for simple CRUD operations. For multi-statement
        transactions prefer ``transaction()``.
        """
        parameters = parameters or ()
        conn_manager = self.kb_conn if db == "kb" else self.mol_conn
        with conn_manager() as conn:
            return conn.execute(sql, parameters).fetchall()

    def count_documents(self) -> int:
        """Return the number of documents currently tracked in the KB queue."""
        rows = self.execute("SELECT COUNT(*) as cnt FROM ingest_queue", db="kb")
        return rows[0]["cnt"] if rows else 0

    def count_molecules(self) -> int:
        """Return the number of molecules currently persisted."""
        rows = self.execute("SELECT COUNT(*) as cnt FROM molecules", db="mol")
        return rows[0]["cnt"] if rows else 0

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

    def _migrate_molecules_v3_to_v4(self, conn: sqlite3.Connection) -> None:
        """v3 -> v4: add evidence table; backfill molecules.canonical_smiles.

        Idempotent: re-running on a v4 schema is a no-op.
        """
        # 1. Backfill canonical_smiles where NULL. At v3 the pipeline already
        #    stored RDKit-canonical SMILES in `smiles`, so the backfill is
        #    just a copy. No RDKit required at migration time.
        conn.execute(
            "UPDATE molecules SET canonical_smiles = smiles "
            "WHERE canonical_smiles IS NULL OR canonical_smiles = ''"
        )
        # 2. Create the evidence table (CREATE IF NOT EXISTS is a no-op if the
        #    schema was just created at v4 — `_EVIDENCE_SCHEMA` is also part
        #    of the molecule_schema() used on greenfield init).
        conn.executescript(_EVIDENCE_SCHEMA)
        # 3. Mirror existing molecule_detections rows into evidence with
        #    kind='figure'. The legacy mol_id is currently NULL on every
        #    pipeline-produced row; we keep it as evidence.mol_id for
        #    back-compat reads and use COALESCE to derive canonical_smiles
        #    from either the parent molecules row or vlm_verified_esmiles.
        conn.execute(
            """
            INSERT OR IGNORE INTO evidence
                (canonical_smiles, mol_id, doc_id, page,
                 bbox_x0, bbox_y0, bbox_x1, bbox_y1,
                 crop_relpath, role, kind, confidence, source_type, created_at)
            SELECT
                COALESCE(NULLIF(m.canonical_smiles, ''), md.vlm_verified_esmiles, ''),
                md.mol_id,
                md.doc_id,
                md.page,
                md.bbox_x0, md.bbox_y0, md.bbox_x1, md.bbox_y1,
                md.crop_relpath,
                'detected',
                'figure',
                md.conf_moldet,
                'image',
                datetime('now')
            FROM molecule_detections md
            LEFT JOIN molecules m ON m.mol_id = md.mol_id
            WHERE md.doc_id IS NOT NULL
              AND COALESCE(NULLIF(m.canonical_smiles, ''), md.vlm_verified_esmiles, '') != ''
            """
        )
        # 4. Mirror existing text_molecule_links rows into evidence with
        #    kind='text'. text_molecule_links.mol_id stores the canonical
        #    SMILES directly (per organizer.py:664 — see
        #    register_molecules_from_text).
        conn.execute(
            """
            INSERT OR IGNORE INTO evidence
                (canonical_smiles, mol_id, doc_id, page,
                 context_text, code_text, role, kind, created_at)
            SELECT
                tml.mol_id,
                tml.mol_id,
                tml.doc_id,
                tml.page,
                tml.text_excerpt,
                tml.code_text,
                COALESCE(tml.role, 'mentioned'),
                'text',
                datetime('now')
            FROM text_molecule_links tml
            WHERE tml.mol_id IS NOT NULL AND tml.mol_id != ''
            """
        )

    def _migrate_molecules_v4_to_v5(self, conn: sqlite3.Connection) -> None:
        """v4 -> v5: add row-alignment columns to the evidence table.

        Each new column has a default NULL so existing rows (inserted by
        Phase 0 page-proximity) are not invalidated. Uses ``PRAGMA
        table_info`` to ensure idempotency — re-running on a v5 schema is
        a no-op.
        """
        existing_cols = {
            r[0] for r in conn.execute("SELECT name FROM pragma_table_info('evidence')")
        }
        for col_def in (
            "row_label TEXT",
            "table_idx INTEGER",
            "row_idx INTEGER",
            "col_idx INTEGER",
        ):
            col_name = col_def.split()[0]
            if col_name not in existing_cols:
                conn.execute(f"ALTER TABLE evidence ADD COLUMN {col_def}")

    @property
    def kb_path(self) -> Path:
        return self._kb_path

    @property
    def mol_path(self) -> Path:
        return self._mol_path


def record_ingest_event(
    db: DatabaseManager,
    *,
    task_id: str,
    doc_id: str | None,
    stage: str,
    level: str,
    message: str,
    data: dict[str, Any] | None = None,
    progress_pct: int | None = None,
    status: str | None = None,
) -> None:
    """Write a pipeline event to the KB ``ingest_logs`` table.

    This is the persistence target for ``runner._maybe_record``. Failures are
    swallowed by the caller so a logging problem never crashes the pipeline.
    """
    import json
    import time

    db.initialize()
    try:
        with db.kb_conn() as conn:
            data_json = json.dumps(data, ensure_ascii=False) if data else None
            conn.execute(
                """
                INSERT INTO ingest_logs
                    (doc_id, stage, level, message, ts_ms, task_id, data)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    doc_id or "",
                    stage,
                    level,
                    message,
                    int(time.time() * 1000),
                    task_id,
                    data_json,
                ),
            )
            if status or progress_pct is not None:
                conn.execute(
                    """
                    UPDATE ingest_queue
                    SET status = COALESCE(?, status),
                        stage = ?,
                        progress_pct = COALESCE(?, progress_pct),
                        updated_at = datetime('now')
                    WHERE id = ?
                    """,
                    (status, stage, progress_pct, task_id),
                )
        logger.debug("Recorded ingest event for %s: %s", task_id, message)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to record ingest event for %s: %s", task_id, exc)
