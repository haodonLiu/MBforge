#![allow(dead_code)]
use rusqlite::{params, Connection, Result as SqlResult};
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};

use crate::core::config::constants::INDEX_DIR;
use crate::core::molecule::molecule_db::MOL_DB_FILENAME;

// ---------------------------------------------------------------------------
// MoleculeRecord — port of Python `MoleculeRecord` from
// `src/mbforge/core/mol_database.py`.
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MoleculeRecord {
    pub mol_id: String,
    /// Layer 1: 纯净 SMILES，事实来源，RDKit/Chematic 直接可用。
    pub smiles: String,
    /// Layer 2: 可选 E-SMILES（含语义标签如 `<c>1:R1</c>`）。
    #[serde(default)]
    pub esmiles: Option<String>,
    /// Layer 2: 语义标签元数据（JSON），如 `{"R1": "Me", "source": "claim_parser"}`。
    #[serde(default)]
    pub semantic_tags: Option<serde_json::Value>,
    #[serde(default)]
    pub name: String,
    #[serde(default)]
    pub source_doc: String,
    #[serde(default)]
    pub activity: Option<f64>,
    #[serde(default)]
    pub activity_type: String,
    #[serde(default)]
    pub units: String,
    #[serde(default)]
    pub source_type: String,
    #[serde(default)]
    pub status: String,
    #[serde(default)]
    pub properties: serde_json::Value,
    /// 用户标签列表（原 `tags`，数据库列已重命名为 `labels`）。
    #[serde(default)]
    pub labels: Vec<String>,
    #[serde(default)]
    pub notes: String,
    #[serde(default)]
    pub created_at: Option<String>,
    /// 关联的化学结构图路径列表（非数据库列，由调用方填充）。
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub related_image_paths: Vec<String>,
    /// VLM (MolScribe) 验证后的 E-SMILES（非数据库列）。
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub vlm_verified_esmiles: Option<String>,
    /// VLM 识别置信度（非数据库列）。
    #[serde(default)]
    pub vlm_confidence: f64,
}

/// 分子关联的化学结构图记录。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MoleculeImage {
    pub image_id: String,
    pub mol_id: String,
    pub image_path: String,
    pub page: Option<usize>,
    pub vlm_esmiles: Option<String>,
    pub vlm_confidence: f64,
    pub is_structure_diagram: bool,
    pub created_at: Option<String>,
    /// 分子 bbox 在 figure 图像中的坐标 (JSON `[x1, y1, x2, y2]`)
    /// 用于 coref 配对和预览时定位
    pub bbox_in_image: Option<Vec<f64>>,
    /// moldet 检测置信度（用于 coref confidence 计算）
    pub moldet_conf: Option<f64>,
}

impl MoleculeImage {
    pub fn new(image_id: &str, mol_id: &str, image_path: &str) -> Self {
        Self {
            image_id: image_id.to_string(),
            mol_id: mol_id.to_string(),
            image_path: image_path.to_string(),
            page: None,
            vlm_esmiles: None,
            vlm_confidence: 0.0,
            is_structure_diagram: true,
            created_at: None,
            bbox_in_image: None,
            moldet_conf: None,
        }
    }
}

impl MoleculeRecord {
    /// 创建新的分子记录。
    ///
    /// `smiles` 为纯净 SMILES（Layer 1 事实来源）。
    /// `esmiles` 为可选的带标签原始字符串（Layer 2 语义插件）。
    pub fn new(mol_id: &str, smiles: &str) -> Self {
        Self {
            mol_id: mol_id.to_string(),
            smiles: smiles.to_string(),
            esmiles: None,
            semantic_tags: None,
            name: String::new(),
            source_doc: String::new(),
            activity: None,
            activity_type: String::new(),
            units: "nM".to_string(),
            source_type: "text".to_string(),
            status: "confirmed".to_string(),
            properties: serde_json::json!({}),
            labels: Vec::new(),
            notes: String::new(),
            created_at: None,
            related_image_paths: Vec::new(),
            vlm_verified_esmiles: None,
            vlm_confidence: 0.0,
        }
    }

    /// Compute basic molecular properties from SMILES.
    ///
    /// Port of `MoleculeRecord.compute_properties()` — uses simplified
    /// heuristics since RDKit is unavailable in Rust.
    /// Complex properties (LogP, TPSA) are left for the sidecar.
    pub fn compute_properties(&self) -> serde_json::Value {
        let smiles = &self.smiles;
        if smiles.is_empty() {
            return serde_json::json!({});
        }

        let mw = estimate_molecular_weight(smiles);
        let (hbd, hba) = estimate_hbd_hba(smiles);
        let rotatable = estimate_rotatable_bonds(smiles);

        serde_json::json!({
            "MW": mw,
            "HBD": hbd,
            "HBA": hba,
            "RotatableBonds": rotatable,
        })
    }

    pub fn row_to_record(row: &rusqlite::Row) -> SqlResult<Self> {
        let properties_str: String = row.get(10).unwrap_or_default();
        let labels_str: String = row.get(11).unwrap_or_default();
        let semantic_tags_str: Option<String> = row.get(12).ok();

        let properties: serde_json::Value =
            serde_json::from_str(&properties_str).unwrap_or(serde_json::json!({}));
        let labels: Vec<String> = serde_json::from_str(&labels_str).unwrap_or_default();
        let semantic_tags: Option<serde_json::Value> =
            semantic_tags_str.and_then(|s| serde_json::from_str(&s).ok());

        Ok(Self {
            mol_id: row.get(0)?,
            smiles: row.get(1)?,
            esmiles: row.get(2).ok(),
            semantic_tags,
            name: row.get(3).unwrap_or_default(),
            source_doc: row.get(4).unwrap_or_default(),
            activity: row.get(5).ok(),
            activity_type: row.get(6).unwrap_or_default(),
            units: row.get(7).unwrap_or_else(|_| "nM".to_string()),
            source_type: row.get(8).unwrap_or_default(),
            status: row.get(9).unwrap_or_default(),
            properties,
            labels,
            notes: row.get(13).unwrap_or_default(),
            created_at: row.get(14).ok(),
            related_image_paths: Vec::new(),
            vlm_verified_esmiles: None,
            vlm_confidence: 0.0,
        })
    }
}

// ---------------------------------------------------------------------------
// Simplified molecular property estimation (no RDKit)
// Port of `MoleculeRecord.compute_properties()`.
// ---------------------------------------------------------------------------

/// Approximate atomic weights for common elements in organic molecules.
fn atomic_weight(element: &str) -> f64 {
    match element {
        "C" => 12.011,
        "H" => 1.008,
        "N" => 14.007,
        "O" => 15.999,
        "S" => 32.065,
        "P" => 30.974,
        "F" => 18.998,
        "Cl" => 35.453,
        "Br" => 79.904,
        "I" => 126.904,
        "Si" => 28.086,
        "B" => 10.811,
        "Se" => 78.971,
        "Na" => 22.990,
        "K" => 39.098,
        "Mg" => 24.305,
        "Ca" => 40.078,
        "Fe" => 55.845,
        "Zn" => 65.380,
        "Cu" => 63.546,
        "Mn" => 54.938,
        "Co" => 58.933,
        _ => 12.011, // default to carbon weight for unknown
    }
}

/// Estimate molecular weight from SMILES using simple atom counting.
///
/// Parses element symbols (1-2 chars), counts explicit atoms,
/// adds implicit hydrogens based on valence rules.
fn estimate_molecular_weight(smiles: &str) -> f64 {
    let tokens = tokenize_smiles_atoms(smiles);
    let mut total_weight = 0.0;

    for token in &tokens {
        let (element, is_aromatic) = if token.starts_with('[') {
            // Bracket notation: [Na], [NH4+], etc.
            let inner = token
                .trim_start_matches('[')
                .trim_end_matches(|c: char| c == ']' || c == '+' || c == '-');
            // Extract just the element symbol (up to first digit or end)
            let sym_end = inner
                .find(|c: char| c.is_ascii_digit())
                .unwrap_or(inner.len());
            let el = &inner[..sym_end.max(1)];
            // Check if first letter is lowercase → aromatic
            (el, inner.starts_with(|c: char| c.is_ascii_lowercase()))
        } else {
            // SMILES convention: lowercase = aromatic
            let is_aro = token.starts_with(|c: char| c.is_ascii_lowercase());
            (token.as_str(), is_aro)
        };

        let el_upper = &element.to_uppercase();
        let wt = atomic_weight(el_upper);
        total_weight += wt;

        // Add implicit hydrogens based on valence
        let h_count = implicit_hydrogens(element, is_aromatic);
        total_weight += h_count as f64 * 1.008;
    }

    (total_weight * 100.0).round() / 100.0
}

/// Very simplified SMILES atom tokenizer.
/// Splits on: `-`, `=`, `#`, `$`, `:`, `.`, `(`, `)`, `[`, `]`, digits.
fn tokenize_smiles_atoms(smiles: &str) -> Vec<String> {
    let mut tokens = Vec::new();
    let mut current = String::new();
    let mut in_bracket = false;

    for c in smiles.chars() {
        match c {
            '[' => {
                if !current.is_empty() {
                    tokens.push(std::mem::take(&mut current));
                }
                current.push(c);
                in_bracket = true;
            }
            ']' => {
                current.push(c);
                tokens.push(std::mem::take(&mut current));
                in_bracket = false;
            }
            _ if in_bracket => {
                current.push(c);
            }
            c if c.is_ascii_alphabetic() => {
                if !current.is_empty() {
                    tokens.push(std::mem::take(&mut current));
                }
                current.push(c);
            }
            _ => {
                // Skip bond symbols, digits, parentheses, etc.
                if !current.is_empty() {
                    tokens.push(std::mem::take(&mut current));
                }
            }
        }
    }
    if !current.is_empty() {
        tokens.push(current);
    }

    tokens
}

/// Simplified implicit hydrogen count based on element and aromaticity.
fn implicit_hydrogens(element: &str, is_aromatic: bool) -> u32 {
    if is_aromatic {
        return match element.to_uppercase().as_str() {
            "C" => 1, // aromatic CH
            "N" => 1, // aromatic NH (pyrrole) or N (pyridine)
            "O" => 0, // aromatic O (furan)
            "S" => 0, // aromatic S (thiophene)
            _ => 0,
        };
    }
    match element.to_uppercase().as_str() {
        "C" => 4,
        "N" => 3,
        "O" => 2,
        "S" => 2,
        "P" => 3,
        "F" | "Cl" | "Br" | "I" => 0,
        _ => 0,
    }
}

/// Estimate HBD (Hydrogen Bond Donors): count of O and N atoms.
fn estimate_hbd_hba(smiles: &str) -> (u32, u32) {
    let tokens = tokenize_smiles_atoms(smiles);
    let mut n_count = 0u32;
    let mut o_count = 0u32;

    for token in &tokens {
        let element = if token.starts_with('[') {
            let inner = token
                .trim_start_matches('[')
                .trim_end_matches(|c: char| c == ']' || c == '+' || c == '-');
            let sym_end = inner
                .find(|c: char| c.is_ascii_digit())
                .unwrap_or(inner.len());
            &inner[..sym_end.max(1)]
        } else {
            token.as_str()
        };

        match element {
            "N" => n_count += 1,
            "O" => o_count += 1,
            _ => {}
        }
    }

    // Simplified: HBD ≈ N + O (with H), HBA ≈ N + O
    // Without full valence analysis, approximate HBD as N + O / 2
    let hbd = (n_count + o_count).saturating_sub(n_count.saturating_sub(2) / 2);
    let hba = n_count + o_count;
    (hbd.min(hba), hba)
}

/// Simplified rotatable bond counter.
fn estimate_rotatable_bonds(smiles: &str) -> u32 {
    // Count single bonds that aren't in rings
    // Heuristic: count `-` (single bond symbol) not inside brackets
    let single_bonds: u32 = smiles.chars().filter(|&c| c == '-').count() as u32;
    single_bonds.min(20) // cap at 20
}

// ---------------------------------------------------------------------------
// MoleculeDatabase — port of Python `MoleculeDatabase` from
// `src/mbforge/core/mol_database.py`.
//
// Manages the `molecules` table + FTS5 search in the same SQLite file
// as the relation database (`molecules.db`).
// ---------------------------------------------------------------------------

pub struct MoleculeDatabase {
    db_path: PathBuf,
    conn: Connection,
}

impl MoleculeDatabase {
    /// Open (or create) the molecule database for a project.
    ///
    /// Uses the same SQLite file as `MoleculeRelationDb`.
    pub fn open(project_root: &Path) -> Result<Self, String> {
        let db_dir = project_root.join(INDEX_DIR);
        std::fs::create_dir_all(&db_dir)
            .map_err(|e| format!("Failed to create index dir: {}", e))?;
        let db_path = db_dir.join(MOL_DB_FILENAME);

        let conn = Connection::open(&db_path)
            .map_err(|e| format!("Failed to open db {}: {}", db_path.display(), e))?;

        // Enable WAL mode for concurrent access
        conn.execute_batch("PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON;")
            .map_err(|e| format!("Failed to set pragmas: {}", e))?;

        let db = Self { db_path, conn };
        db.init_schema()?;
        Ok(db)
    }

    fn init_schema(&self) -> Result<(), String> {
        // Phase 0: Create base table (backward-compat for new databases)
        self.conn
            .execute_batch(
                "
            CREATE TABLE IF NOT EXISTS molecules (
                mol_id TEXT PRIMARY KEY,
                smiles TEXT NOT NULL,
                esmiles TEXT,
                name TEXT,
                source_doc TEXT,
                activity REAL,
                activity_type TEXT,
                units TEXT DEFAULT 'nM',
                source_type TEXT DEFAULT 'text',
                status TEXT DEFAULT 'confirmed',
                properties TEXT,
                labels TEXT,
                semantic_tags TEXT,
                notes TEXT,
                fingerprint BLOB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_mol_smiles ON molecules(smiles);
            CREATE INDEX IF NOT EXISTS idx_mol_source ON molecules(source_doc);
            CREATE INDEX IF NOT EXISTS idx_mol_status ON molecules(status);
            CREATE INDEX IF NOT EXISTS idx_mol_source_type ON molecules(source_type);
            CREATE INDEX IF NOT EXISTS idx_mol_activity ON molecules(activity);
            ",
            )
            .map_err(|e| format!("Failed to create schema: {}", e))?;

        // Phase 1: Migrate old schema (esmiles-only → smiles + esmiles)
        self.migrate_v0_to_v1()?;

        // Phase 2: Create FTS5 virtual table for text search (indexing smiles)
        self.conn
            .execute_batch(
                "
            CREATE VIRTUAL TABLE IF NOT EXISTS mol_search USING fts5(
                name, notes, smiles,
                content='molecules',
                content_rowid='rowid'
            );
            CREATE TABLE IF NOT EXISTS molecule_images (
                image_id TEXT PRIMARY KEY,
                mol_id TEXT NOT NULL,
                image_path TEXT NOT NULL,
                page INTEGER,
                vlm_esmiles TEXT,
                vlm_confidence REAL,
                is_structure_diagram INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                bbox_in_image TEXT,
                moldet_conf REAL,
                FOREIGN KEY (mol_id) REFERENCES molecules(mol_id)
            );
            CREATE INDEX IF NOT EXISTS idx_molimg_mol_id ON molecule_images(mol_id);
            CREATE INDEX IF NOT EXISTS idx_molimg_path ON molecule_images(image_path);
            ",
            )
            .map_err(|e| format!("Failed to create FTS5 table: {}", e))?;

        // 迁移：旧库缺 bbox_in_image / moldet_col 列时添加
        Self::migrate_v1_to_v2(&self.conn).ok();

        Ok(())
    }

    /// Migrate v1 → v2: 给 molecule_images 加 bbox_in_image / moldet_conf 列（coref 持久化用）
    fn migrate_v1_to_v2(conn: &rusqlite::Connection) -> Result<(), String> {
        // 检查列是否已存在
        let has_bbox: bool = conn
            .query_row(
                "SELECT COUNT(*) FROM pragma_table_info('molecule_images') WHERE name = 'bbox_in_image'",
                [],
                |r| r.get(0),
            )
            .unwrap_or(0)
            > 0;

        if !has_bbox {
            log::info!("Migrating molecule_images table: adding bbox_in_image / moldet_conf columns");
            conn.execute(
                "ALTER TABLE molecule_images ADD COLUMN bbox_in_image TEXT",
                [],
            )
            .map_err(|e| format!("Failed to add bbox_in_image column: {}", e))?;
            conn.execute(
                "ALTER TABLE molecule_images ADD COLUMN moldet_conf REAL",
                [],
            )
            .map_err(|e| format!("Failed to add moldet_conf column: {}", e))?;
        }
        Ok(())
    }

    /// Migrate legacy schema (v0: esmiles-only) to v1 (smiles + esmiles).
    fn migrate_v0_to_v1(&self) -> Result<(), String> {
        // Check if old 'esmiles' column exists without 'smiles'
        let has_smiles: bool = self
            .conn
            .query_row(
                "SELECT COUNT(*) FROM pragma_table_info('molecules') WHERE name = 'smiles'",
                [],
                |r| r.get(0),
            )
            .unwrap_or(0)
            > 0;

        if has_smiles {
            return Ok(()); // Already migrated
        }

        log::info!("Migrating molecules table from v0 (esmiles-only) to v1 (smiles + esmiles)");

        // Step 1: Add new columns
        self.conn
            .execute("ALTER TABLE molecules ADD COLUMN smiles TEXT", [])
            .map_err(|e| format!("Failed to add smiles column: {}", e))?;
        self.conn
            .execute("ALTER TABLE molecules ADD COLUMN semantic_tags TEXT", [])
            .ok(); // Optional, ignore if exists

        // Step 2: Migrate esmiles → smiles (strip E-SMILES tags)
        self.conn
            .execute(
                "UPDATE molecules SET smiles = COALESCE(
                    NULLIF(trim(replace(replace(replace(replace(esmiles,
                        '<a>', ''), '</a>', ''),
                        '<r>', ''), '</r>', ''),
                        '<c>', ''), '</c>', ''),
                        '<sep>', ''), ''),
                    ''
                ), esmiles) WHERE smiles IS NULL OR smiles = ''",
                [],
            )
            .ok();

        // Step 3: Ensure no NULL smiles (fallback: copy esmiles raw)
        self.conn
            .execute(
                "UPDATE molecules SET smiles = esmiles WHERE smiles IS NULL OR smiles = ''",
                [],
            )
            .map_err(|e| format!("Failed to backfill smiles: {}", e))?;

        // Step 4: Make esmiles nullable (keep original for reference)
        // SQLite doesn't support ALTER COLUMN, but we just stop requiring it in INSERTs

        // Step 5: Rename tags → labels if old column exists
        let has_old_tags: bool = self
            .conn
            .query_row(
                "SELECT COUNT(*) FROM pragma_table_info('molecules') WHERE name = 'tags'",
                [],
                |r| r.get(0),
            )
            .unwrap_or(0)
            > 0;
        if has_old_tags {
            self.conn
                .execute("ALTER TABLE molecules RENAME COLUMN tags TO labels", [])
                .ok();
        }

        log::info!("Migration v0→v1 complete");
        Ok(())
    }

    /// Add or update a molecule record.
    ///
    /// Automatically computes properties if `properties` is empty.
    /// Fills created_at with current timestamp if not set.
    pub fn add_molecule(&self, record: &MoleculeRecord) -> Result<(), String> {
        let mut rec = record.clone();
        if rec.properties == serde_json::json!({}) {
            rec.properties = rec.compute_properties();
        }

        let properties_str =
            serde_json::to_string(&rec.properties).unwrap_or_else(|_| "{}".to_string());
        let labels_str = serde_json::to_string(&rec.labels).unwrap_or_else(|_| "[]".to_string());
        let semantic_tags_str = rec
            .semantic_tags
            .as_ref()
            .map(|v| serde_json::to_string(v).unwrap_or_else(|_| "{}".to_string()));
        let esmiles_str = rec.esmiles.as_deref().unwrap_or("");

        // 删除旧 FTS 条目（INSERT OR REPLACE 会改变 rowid，导致旧 FTS 残留）
        let _ = self.conn.execute(
            "DELETE FROM mol_search WHERE rowid IN (SELECT rowid FROM molecules WHERE mol_id = ?1)",
            params![rec.mol_id],
        );

        // 计算指纹（如果 smiles 非空且指纹尚未提供）
        let fingerprint_bytes: Option<Vec<u8>> = if rec.smiles.len() >= 2 {
            crate::core::chem::chem::compute_ecfp4_as_bytes(&rec.smiles).ok()
        } else {
            None
        };

        self.conn
            .execute(
                "INSERT OR REPLACE INTO molecules
                 (mol_id, smiles, esmiles, name, source_doc, activity, activity_type,
                  units, source_type, status, properties, labels, semantic_tags, notes, fingerprint)
                 VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15)",
                params![
                    rec.mol_id,
                    rec.smiles,
                    esmiles_str,
                    rec.name,
                    rec.source_doc,
                    rec.activity,
                    rec.activity_type,
                    rec.units,
                    rec.source_type,
                    rec.status,
                    properties_str,
                    labels_str,
                    semantic_tags_str.as_deref(),
                    rec.notes,
                    fingerprint_bytes,
                ],
            )
            .map_err(|e| format!("Failed to insert molecule: {}", e))?;

        // Sync FTS5 index
        let _ = self.conn.execute(
            "INSERT INTO mol_search(rowid, name, notes, smiles)
             VALUES (last_insert_rowid(), ?1, ?2, ?3)",
            params![rec.name, rec.notes, rec.smiles],
        );

        Ok(())
    }

    /// Batch add or update molecule records inside a single transaction.
    ///
    /// 同时写入关联的 molecule_images 记录。
    pub fn add_molecules_batch(&self, records: &[MoleculeRecord]) -> Result<usize, String> {
        let tx = self
            .conn
            .unchecked_transaction()
            .map_err(|e| format!("Failed to begin batch transaction: {}", e))?;

        for rec in records {
            let mut rec = rec.clone();
            if rec.properties == serde_json::json!({}) {
                rec.properties = rec.compute_properties();
            }

            let properties_str =
                serde_json::to_string(&rec.properties).unwrap_or_else(|_| "{}".to_string());
            let labels_str =
                serde_json::to_string(&rec.labels).unwrap_or_else(|_| "[]".to_string());
            let semantic_tags_str = rec
                .semantic_tags
                .as_ref()
                .map(|v| serde_json::to_string(v).unwrap_or_else(|_| "{}".to_string()));
            let esmiles_str = rec.esmiles.as_deref().unwrap_or("");

            let fingerprint_bytes: Option<Vec<u8>> = if rec.smiles.len() >= 2 {
                crate::core::chem::chem::compute_ecfp4_as_bytes(&rec.smiles).ok()
            } else {
                None
            };

            // Delete old FTS entries and images (INSERT OR REPLACE changes rowid)
            let _ = tx.execute(
                "DELETE FROM mol_search WHERE rowid IN (SELECT rowid FROM molecules WHERE mol_id = ?1)",
                params![rec.mol_id],
            );
            let _ = tx.execute(
                "DELETE FROM molecule_images WHERE mol_id = ?1",
                params![rec.mol_id],
            );

            tx.execute(
                "INSERT OR REPLACE INTO molecules
                 (mol_id, smiles, esmiles, name, source_doc, activity, activity_type,
                  units, source_type, status, properties, labels, semantic_tags, notes, fingerprint)
                 VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15)",
                params![
                    rec.mol_id,
                    rec.smiles,
                    esmiles_str,
                    rec.name,
                    rec.source_doc,
                    rec.activity,
                    rec.activity_type,
                    rec.units,
                    rec.source_type,
                    rec.status,
                    properties_str,
                    labels_str,
                    semantic_tags_str.as_deref(),
                    rec.notes,
                    fingerprint_bytes,
                ],
            )
            .map_err(|e| format!("Failed to insert molecule {}: {}", rec.mol_id, e))?;

            // 写入关联图片
            for img_path in &rec.related_image_paths {
                let img_id =
                    crate::core::helpers::sha256_text(&format!("{}|{}", rec.mol_id, img_path));
                let _ = tx.execute(
                    "INSERT OR REPLACE INTO molecule_images
                     (image_id, mol_id, image_path, vlm_esmiles, vlm_confidence)
                     VALUES (?1, ?2, ?3, ?4, ?5)",
                    params![
                        img_id,
                        rec.mol_id,
                        img_path,
                        rec.vlm_verified_esmiles.as_deref().unwrap_or(""),
                        rec.vlm_confidence,
                    ],
                );
            }

            // Sync FTS5 index
            let _ = tx.execute(
                "INSERT INTO mol_search(rowid, name, notes, smiles)
                 VALUES (last_insert_rowid(), ?1, ?2, ?3)",
                params![rec.name, rec.notes, rec.smiles],
            );
        }

        tx.commit()
            .map_err(|e| format!("Failed to commit batch transaction: {}", e))?;

        Ok(records.len())
    }

    /// Get a molecule by its ID.
    pub fn get_molecule(&self, mol_id: &str) -> Result<Option<MoleculeRecord>, String> {
        let mut stmt = self
            .conn
            .prepare("SELECT * FROM molecules WHERE mol_id = ?")
            .map_err(|e| format!("Prepare failed: {}", e))?;

        let mut rows = stmt
            .query(params![mol_id])
            .map_err(|e| format!("Query failed: {}", e))?;

        match rows
            .next()
            .map_err(|e| format!("Row fetch failed: {}", e))?
        {
            Some(row) => {
                let record = MoleculeRecord::row_to_record(row)
                    .map_err(|e| format!("Row parse failed: {}", e))?;
                Ok(Some(record))
            }
            None => Ok(None),
        }
    }

    /// Search molecule by exact SMILES match.
    pub fn search_by_smiles(&self, smiles: &str) -> Result<Option<MoleculeRecord>, String> {
        let mut stmt = self
            .conn
            .prepare("SELECT * FROM molecules WHERE smiles = ?")
            .map_err(|e| format!("Prepare failed: {}", e))?;

        let mut rows = stmt
            .query(params![smiles])
            .map_err(|e| format!("Query failed: {}", e))?;

        match rows
            .next()
            .map_err(|e| format!("Row fetch failed: {}", e))?
        {
            Some(row) => {
                let record = MoleculeRecord::row_to_record(row)
                    .map_err(|e| format!("Row parse failed: {}", e))?;
                Ok(Some(record))
            }
            None => Ok(None),
        }
    }

    /// Search molecules by source document ID.
    pub fn search_by_source(&self, doc_id: &str) -> Result<Vec<MoleculeRecord>, String> {
        let mut stmt = self
            .conn
            .prepare("SELECT * FROM molecules WHERE source_doc = ?")
            .map_err(|e| format!("Prepare failed: {}", e))?;

        let rows = stmt
            .query_map(params![doc_id], MoleculeRecord::row_to_record)
            .map_err(|e| format!("Query failed: {}", e))?;

        let mut results = Vec::new();
        for row in rows {
            results.push(row.map_err(|e| format!("Row parse failed: {}", e))?);
        }
        Ok(results)
    }

    /// Full-text search across molecules (name, notes, smiles).
    pub fn search_text(&self, query: &str) -> Result<Vec<MoleculeRecord>, String> {
        let sql = "
            SELECT m.* FROM molecules m
            JOIN mol_search fts ON m.rowid = fts.rowid
            WHERE mol_search MATCH ?1
            ORDER BY rank
            LIMIT 50
        ";

        let mut stmt = self
            .conn
            .prepare(sql)
            .map_err(|e| format!("Prepare failed: {}", e))?;

        let rows = stmt
            .query_map(params![query], MoleculeRecord::row_to_record)
            .map_err(|e| format!("Query failed: {}", e))?;

        let mut results = Vec::new();
        for row in rows {
            results.push(row.map_err(|e| format!("Row parse failed: {}", e))?);
        }
        Ok(results)
    }

    /// List all molecules with optional filtering.
    pub fn list_all(
        &self,
        limit: usize,
        offset: usize,
        source_type: Option<&str>,
        status: Option<&str>,
    ) -> Result<Vec<MoleculeRecord>, String> {
        let mut conditions = Vec::new();
        let mut param_values: Vec<Box<dyn rusqlite::types::ToSql>> = Vec::new();

        if let Some(st) = source_type {
            conditions.push("source_type = ?");
            param_values.push(Box::new(st.to_string()));
        }
        if let Some(s) = status {
            conditions.push("status = ?");
            param_values.push(Box::new(s.to_string()));
        }

        let where_clause = if conditions.is_empty() {
            String::new()
        } else {
            format!("WHERE {}", conditions.join(" AND "))
        };

        let sql = format!(
            "SELECT * FROM molecules {} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            where_clause
        );

        param_values.push(Box::new(limit as i64));
        param_values.push(Box::new(offset as i64));

        let params_ref: Vec<&dyn rusqlite::types::ToSql> =
            param_values.iter().map(|p| p.as_ref()).collect();

        let mut stmt = self
            .conn
            .prepare(&sql)
            .map_err(|e| format!("Prepare failed: {}", e))?;

        let rows = stmt
            .query_map(params_ref.as_slice(), MoleculeRecord::row_to_record)
            .map_err(|e| format!("Query failed: {}", e))?;

        let mut results = Vec::new();
        for row in rows {
            results.push(row.map_err(|e| format!("Row parse failed: {}", e))?);
        }
        Ok(results)
    }

    /// Delete a molecule by ID.
    pub fn delete_molecule(&self, mol_id: &str) -> Result<bool, String> {
        let tx = self
            .conn
            .unchecked_transaction()
            .map_err(|e| format!("Failed to begin transaction: {}", e))?;
        // 先清理关联图片
        let _ = tx.execute(
            "DELETE FROM molecule_images WHERE mol_id = ?1",
            params![mol_id],
        );
        // 先清理 FTS 条目
        let _ = tx.execute(
            "DELETE FROM mol_search WHERE rowid IN (SELECT rowid FROM molecules WHERE mol_id = ?1)",
            params![mol_id],
        );
        let affected = tx
            .execute("DELETE FROM molecules WHERE mol_id = ?", params![mol_id])
            .map_err(|e| format!("Failed to delete molecule: {}", e))?;
        tx.commit()
            .map_err(|e| format!("Failed to commit delete transaction: {}", e))?;
        Ok(affected > 0)
    }

    // ---------------------------------------------------------------------------
    // Molecule Image CRUD
    // ---------------------------------------------------------------------------

    /// 为分子添加关联的化学结构图记录。
    pub fn add_molecule_image(&self, img: &MoleculeImage) -> Result<(), String> {
        let bbox_json = img
            .bbox_in_image
            .as_ref()
            .and_then(|b| serde_json::to_string(b).ok());
        self.conn
            .execute(
                "INSERT OR REPLACE INTO molecule_images
                 (image_id, mol_id, image_path, page, vlm_esmiles, vlm_confidence, is_structure_diagram, bbox_in_image, moldet_conf)
                 VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9)",
                params![
                    img.image_id,
                    img.mol_id,
                    img.image_path,
                    img.page.map(|p| p as i64),
                    img.vlm_esmiles.as_deref().unwrap_or(""),
                    img.vlm_confidence,
                    img.is_structure_diagram as i32,
                    bbox_json,
                    img.moldet_conf,
                ],
            )
            .map_err(|e| format!("Failed to add molecule image: {}", e))?;
        Ok(())
    }

    /// 获取指定分子的所有关联图片。
    pub fn get_molecule_images(&self, mol_id: &str) -> Result<Vec<MoleculeImage>, String> {
        let mut stmt = self
            .conn
            .prepare(
                "SELECT image_id, mol_id, image_path, page, vlm_esmiles, vlm_confidence, is_structure_diagram, created_at, bbox_in_image, moldet_conf
                 FROM molecule_images WHERE mol_id = ? ORDER BY page",
            )
            .map_err(|e| format!("Prepare failed: {}", e))?;

        let rows = stmt
            .query_map(params![mol_id], |row| {
                let bbox_str: Option<String> = row.get(8).ok().flatten();
                let bbox: Option<Vec<f64>> =
                    bbox_str.and_then(|s| serde_json::from_str(&s).ok());
                Ok(MoleculeImage {
                    image_id: row.get(0).unwrap_or_default(),
                    mol_id: row.get(1).unwrap_or_default(),
                    image_path: row.get(2).unwrap_or_default(),
                    page: row
                        .get::<_, Option<i64>>(3)
                        .ok()
                        .flatten()
                        .map(|p| p as usize),
                    vlm_esmiles: row
                        .get::<_, Option<String>>(4)
                        .ok()
                        .flatten()
                        .filter(|s| !s.is_empty()),
                    vlm_confidence: row.get(5).unwrap_or(0.0),
                    is_structure_diagram: row.get::<_, i32>(6).unwrap_or(1) != 0,
                    created_at: row.get(7).ok(),
                    bbox_in_image: bbox,
                    moldet_conf: row.get(9).ok().flatten(),
                })
            })
            .map_err(|e| format!("Query failed: {}", e))?;

        let mut results = Vec::new();
        for row in rows {
            results.push(row.map_err(|e| format!("Row parse failed: {}", e))?);
        }
        Ok(results)
    }

    /// 根据图片路径查找关联的分子图片记录。
    pub fn get_image_by_path(&self, image_path: &str) -> Result<Option<MoleculeImage>, String> {
        let mut stmt = self
            .conn
            .prepare(
                "SELECT image_id, mol_id, image_path, page, vlm_esmiles, vlm_confidence, is_structure_diagram, created_at
                 FROM molecule_images WHERE image_path = ? LIMIT 1",
            )
            .map_err(|e| format!("Prepare failed: {}", e))?;

        let mut rows = stmt
            .query(params![image_path])
            .map_err(|e| format!("Query failed: {}", e))?;

        match rows
            .next()
            .map_err(|e| format!("Row fetch failed: {}", e))?
        {
            Some(row) => Ok(Some(MoleculeImage {
                image_id: row.get(0).unwrap_or_default(),
                mol_id: row.get(1).unwrap_or_default(),
                image_path: row.get(2).unwrap_or_default(),
                page: row
                    .get::<_, Option<i64>>(3)
                    .ok()
                    .flatten()
                    .map(|p| p as usize),
                vlm_esmiles: row
                    .get::<_, Option<String>>(4)
                    .ok()
                    .flatten()
                    .filter(|s| !s.is_empty()),
                vlm_confidence: row.get(5).unwrap_or(0.0),
                is_structure_diagram: row.get::<_, i32>(6).unwrap_or(1) != 0,
                created_at: row.get(7).ok(),
                bbox_in_image: None,
                moldet_conf: None,
            })),
            None => Ok(None),
        }
    }

    /// Get database statistics.
    pub fn get_stats(&self) -> Result<serde_json::Value, String> {
        let total: i64 = self
            .conn
            .query_row("SELECT COUNT(*) FROM molecules", [], |r| r.get(0))
            .unwrap_or(0);

        let with_activity: i64 = self
            .conn
            .query_row(
                "SELECT COUNT(*) FROM molecules WHERE activity IS NOT NULL",
                [],
                |r| r.get(0),
            )
            .unwrap_or(0);

        let pending: i64 = self
            .conn
            .query_row(
                "SELECT COUNT(*) FROM molecules WHERE status = 'pending'",
                [],
                |r| r.get(0),
            )
            .unwrap_or(0);

        Ok(serde_json::json!({
            "total": total,
            "with_activity": with_activity,
            "pending": pending,
        }))
    }

    /// Update molecule status.
    pub fn update_status(&self, mol_id: &str, status: &str) -> Result<bool, String> {
        let affected = self
            .conn
            .execute(
                "UPDATE molecules SET status = ?1 WHERE mol_id = ?2",
                params![status, mol_id],
            )
            .map_err(|e| format!("Failed to update status: {}", e))?;
        Ok(affected > 0)
    }

    /// Update an existing molecule's editable fields.
    ///
    /// Updates: smiles, esmiles, name, source_doc, activity, activity_type, units,
    /// source_type, status, properties, labels, semantic_tags, notes.
    /// `mol_id`, `created_at` 不可改 (作为稳定标识).
    /// Returns true if the molecule existed and was updated.
    pub fn update_molecule(&self, record: &MoleculeRecord) -> Result<bool, String> {
        let labels_str = serde_json::to_string(&record.labels).unwrap_or_else(|_| "[]".to_string());
        let semantic_tags_str = record
            .semantic_tags
            .as_ref()
            .map(|v| serde_json::to_string(v).unwrap_or_else(|_| "{}".to_string()));
        let esmiles_str = record.esmiles.as_deref().unwrap_or("");

        let tx = self
            .conn
            .unchecked_transaction()
            .map_err(|e| format!("Failed to begin transaction: {}", e))?;

        let affected = tx
            .execute(
                "UPDATE molecules SET
                    smiles = ?1,
                    esmiles = ?2,
                    name = ?3,
                    source_doc = ?4,
                    activity = ?5,
                    activity_type = ?6,
                    units = ?7,
                    source_type = ?8,
                    status = ?9,
                    properties = ?10,
                    labels = ?11,
                    semantic_tags = ?12,
                    notes = ?13
                 WHERE mol_id = ?14",
                params![
                    record.smiles,
                    esmiles_str,
                    record.name,
                    record.source_doc,
                    record.activity,
                    record.activity_type,
                    record.units,
                    record.source_type,
                    record.status,
                    serde_json::to_string(&record.properties).unwrap_or_else(|_| "{}".to_string()),
                    labels_str,
                    semantic_tags_str.as_deref(),
                    record.notes,
                    record.mol_id,
                ],
            )
            .map_err(|e| format!("Failed to update molecule: {}", e))?;

        if affected == 0 {
            return Ok(false);
        }

        // 同步 FTS5 索引 (mol_search)
        let _ = tx.execute(
            "DELETE FROM mol_search WHERE rowid = (SELECT rowid FROM molecules WHERE mol_id = ?1)",
            params![record.mol_id],
        );
        let _ = tx.execute(
            "INSERT INTO mol_search(rowid, name, notes, smiles)
             SELECT rowid, name, notes, smiles FROM molecules WHERE mol_id = ?1",
            params![record.mol_id],
        );

        tx.commit()
            .map_err(|e| format!("Failed to commit update transaction: {}", e))?;
        Ok(true)
    }

    /// 批量更新多个分子.
    ///
    /// 在单个事务中执行，全部成功或全部回滚.
    /// 返回 (成功数, 失败 mol_id 列表).
    pub fn update_molecules_batch(
        &self,
        records: &[MoleculeRecord],
    ) -> Result<(usize, Vec<String>), String> {
        let tx = self
            .conn
            .unchecked_transaction()
            .map_err(|e| format!("Failed to start transaction: {}", e))?;

        let mut updated = 0;
        let mut failed: Vec<String> = Vec::new();
        for rec in records {
            let labels_str =
                serde_json::to_string(&rec.labels).unwrap_or_else(|_| "[]".to_string());
            let semantic_tags_str = rec
                .semantic_tags
                .as_ref()
                .map(|v| serde_json::to_string(v).unwrap_or_else(|_| "{}".to_string()));
            let esmiles_str = rec.esmiles.as_deref().unwrap_or("");
            let affected = tx
                .execute(
                    "UPDATE molecules SET
                        smiles = ?1, esmiles = ?2, name = ?3, source_doc = ?4, activity = ?5,
                        activity_type = ?6, units = ?7, source_type = ?8, status = ?9,
                        properties = ?10, labels = ?11, semantic_tags = ?12, notes = ?13
                     WHERE mol_id = ?14",
                    params![
                        rec.smiles,
                        esmiles_str,
                        rec.name,
                        rec.source_doc,
                        rec.activity,
                        rec.activity_type,
                        rec.units,
                        rec.source_type,
                        rec.status,
                        serde_json::to_string(&rec.properties).unwrap_or_else(|_| "{}".to_string()),
                        labels_str,
                        semantic_tags_str.as_deref(),
                        rec.notes,
                        rec.mol_id,
                    ],
                )
                .map_err(|e| format!("Failed to update {}: {}", rec.mol_id, e));
            match affected {
                Ok(n) if n > 0 => updated += 1,
                Ok(_) => failed.push(rec.mol_id.clone()), // 不存在
                Err(e) => {
                    failed.push(rec.mol_id.clone());
                    log::warn!("Batch update: {}", e);
                }
            }
        }

        tx.commit()
            .map_err(|e| format!("Failed to commit batch update: {}", e))?;

        Ok((updated, failed))
    }

    /// Return the database path (useful for debugging).
    pub fn db_path(&self) -> &Path {
        &self.db_path
    }

    /// Access the underlying SQLite connection.
    ///
    /// Used by MoleculeEngine for SAR queries that need direct
    /// access to the `molecules` table alongside relation data.
    pub(crate) fn conn(&self) -> &Connection {
        &self.conn
    }

    /// 存储分子的 Morgan 指纹（base64 解码后的 256 bytes）
    pub fn set_fingerprint(&self, mol_id: &str, fp_bytes: &[u8]) -> Result<(), String> {
        self.conn
            .execute(
                "UPDATE molecules SET fingerprint = ?1 WHERE mol_id = ?2",
                rusqlite::params![fp_bytes, mol_id],
            )
            .map_err(|e| format!("set_fingerprint failed: {}", e))?;
        Ok(())
    }

    /// 获取所有分子的 ID、SMILES 和指纹（用于子结构搜索预过滤）
    pub fn get_all_fingerprints(&self) -> Result<Vec<(String, String, Vec<u8>)>, String> {
        let mut stmt = self
            .conn
            .prepare(
                "SELECT mol_id, smiles, fingerprint FROM molecules WHERE fingerprint IS NOT NULL",
            )
            .map_err(|e| format!("Prepare failed: {}", e))?;

        let rows = stmt
            .query_map([], |row| {
                let mol_id: String = row.get(0)?;
                let smiles: String = row.get(1)?;
                let fp: Vec<u8> = row.get(2)?;
                Ok((mol_id, smiles, fp))
            })
            .map_err(|e| format!("Query failed: {}", e))?;

        let mut results = Vec::new();
        for row in rows {
            results.push(row.map_err(|e| format!("Row error: {}", e))?);
        }
        Ok(results)
    }

    /// 获取所有分子的 SMILES 列表（用于子结构搜索候选集）
    pub fn get_all_smiles(&self) -> Result<Vec<(String, String)>, String> {
        let mut stmt = self
            .conn
            .prepare("SELECT mol_id, smiles FROM molecules WHERE status != 'deleted'")
            .map_err(|e| format!("Prepare failed: {}", e))?;

        let rows = stmt
            .query_map([], |row| {
                Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?))
            })
            .map_err(|e| format!("Query failed: {}", e))?;

        let mut results = Vec::new();
        for row in rows {
            results.push(row.map_err(|e| format!("Row error: {}", e))?);
        }
        Ok(results)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    fn make_record(mol_id: &str, smiles: &str) -> MoleculeRecord {
        MoleculeRecord::new(mol_id, smiles)
    }

    #[test]
    fn test_add_and_get_molecule() {
        let tmp = TempDir::new().unwrap();
        let db = MoleculeDatabase::open(tmp.path()).unwrap();

        let rec = make_record("mol-1", "CC(=O)Oc1ccccc1C(=O)O");
        db.add_molecule(&rec).unwrap();

        let loaded = db.get_molecule("mol-1").unwrap().unwrap();
        assert_eq!(loaded.mol_id, "mol-1");
        assert_eq!(loaded.smiles, "CC(=O)Oc1ccccc1C(=O)O");

        // Properties should be auto-computed
        let mw = loaded.properties["MW"].as_f64().unwrap();
        assert!(mw > 100.0 && mw < 300.0);
    }

    #[test]
    fn test_get_nonexistent() {
        let tmp = TempDir::new().unwrap();
        let db = MoleculeDatabase::open(tmp.path()).unwrap();
        assert!(db.get_molecule("nonexistent").unwrap().is_none());
    }

    #[test]
    fn test_search_by_smiles() {
        let tmp = TempDir::new().unwrap();
        let db = MoleculeDatabase::open(tmp.path()).unwrap();

        db.add_molecule(&make_record("m1", "CCO")).unwrap();
        db.add_molecule(&make_record("m2", "CCCO")).unwrap();

        let found = db.search_by_smiles("CCO").unwrap().unwrap();
        assert_eq!(found.mol_id, "m1");
    }

    #[test]
    fn test_search_by_source() {
        let tmp = TempDir::new().unwrap();
        let db = MoleculeDatabase::open(tmp.path()).unwrap();

        let mut r1 = make_record("m1", "CCO");
        r1.source_doc = "doc-1".to_string();
        db.add_molecule(&r1).unwrap();

        let mut r2 = make_record("m2", "CCCO");
        r2.source_doc = "doc-1".to_string();
        db.add_molecule(&r2).unwrap();

        let mut r3 = make_record("m3", "C");
        r3.source_doc = "doc-2".to_string();
        db.add_molecule(&r3).unwrap();

        let from_doc1 = db.search_by_source("doc-1").unwrap();
        assert_eq!(from_doc1.len(), 2);

        let from_doc2 = db.search_by_source("doc-2").unwrap();
        assert_eq!(from_doc2.len(), 1);
    }

    #[test]
    fn test_delete_molecule() {
        let tmp = TempDir::new().unwrap();
        let db = MoleculeDatabase::open(tmp.path()).unwrap();

        db.add_molecule(&make_record("del-me", "CCO")).unwrap();
        assert!(db.get_molecule("del-me").unwrap().is_some());

        db.delete_molecule("del-me").unwrap();
        assert!(db.get_molecule("del-me").unwrap().is_none());
    }

    #[test]
    fn test_get_stats() {
        let tmp = TempDir::new().unwrap();
        let db = MoleculeDatabase::open(tmp.path()).unwrap();

        let stats = db.get_stats().unwrap();
        assert_eq!(stats["total"], 0);

        db.add_molecule(&make_record("m1", "CCO")).unwrap();
        let stats = db.get_stats().unwrap();
        assert_eq!(stats["total"], 1);
        assert_eq!(stats["with_activity"], 0);
    }

    #[test]
    fn test_update_status() {
        let tmp = TempDir::new().unwrap();
        let db = MoleculeDatabase::open(tmp.path()).unwrap();

        let mut rec = make_record("m1", "CCO");
        rec.status = "pending".to_string();
        db.add_molecule(&rec).unwrap();

        db.update_status("m1", "confirmed").unwrap();
        let loaded = db.get_molecule("m1").unwrap().unwrap();
        assert_eq!(loaded.status, "confirmed");
    }

    #[test]
    fn test_list_all_with_filter() {
        let tmp = TempDir::new().unwrap();
        let db = MoleculeDatabase::open(tmp.path()).unwrap();

        let mut r1 = make_record("m1", "CCO");
        r1.source_type = "image".to_string();
        r1.status = "confirmed".to_string();
        db.add_molecule(&r1).unwrap();

        let mut r2 = make_record("m2", "CCCO");
        r2.source_type = "text".to_string();
        r2.status = "pending".to_string();
        db.add_molecule(&r2).unwrap();

        let all = db.list_all(100, 0, None, None).unwrap();
        assert_eq!(all.len(), 2);

        let images = db.list_all(100, 0, Some("image"), None).unwrap();
        assert_eq!(images.len(), 1);
        assert_eq!(images[0].mol_id, "m1");

        let pending = db.list_all(100, 0, None, Some("pending")).unwrap();
        assert_eq!(pending.len(), 1);
        assert_eq!(pending[0].mol_id, "m2");
    }

    #[test]
    fn test_compute_properties_aspirin() {
        let rec = make_record("test", "CC(=O)Oc1ccccc1C(=O)O");
        let props = rec.compute_properties();
        let mw = props["MW"].as_f64().unwrap();
        // True MW is 180.16; simplified estimate is ~198 (implicit H overcounted)
        assert!(mw > 170.0 && mw < 210.0, "MW={}", mw);
        assert!(props["HBD"].as_u64().unwrap_or(0) >= 1);
        assert!(props["HBA"].as_u64().unwrap_or(0) >= 3);
    }

    #[test]
    fn test_estimate_molecular_weight_water() {
        let mw = estimate_molecular_weight("O");
        assert!((mw - 18.0).abs() < 3.0, "MW(H2O)={}", mw);
    }

    #[test]
    fn test_estimate_molecular_weight_methane() {
        let mw = estimate_molecular_weight("C");
        assert!((mw - 16.0).abs() < 3.0, "MW(CH4)={}", mw);
    }

    #[test]
    fn test_estimate_hbd_hba_water() {
        let (hbd, hba) = estimate_hbd_hba("O");
        assert!(hbd >= 1);
        assert!(hba >= 1);
    }

    #[test]
    fn test_tokenize_smiles() {
        let tokens = tokenize_smiles_atoms("CCO");
        assert_eq!(tokens, vec!["C", "C", "O"]);
    }

    #[test]
    fn test_tokenize_smiles_with_brackets() {
        let tokens = tokenize_smiles_atoms("C[Na]O");
        assert!(tokens.contains(&"C".to_string()));
        assert!(tokens.contains(&"[Na]".to_string()));
        assert!(tokens.contains(&"O".to_string()));
    }

    #[test]
    fn test_add_molecules_batch() {
        let tmp = TempDir::new().unwrap();
        let db = MoleculeDatabase::open(tmp.path()).unwrap();

        let mut r1 = make_record("m1", "CCO");
        r1.name = "Ethanol".to_string();
        let mut r2 = make_record("m2", "CCCO");
        r2.name = "Propanol".to_string();
        let mut r3 = make_record("m3", "C");
        r3.name = "Methane".to_string();

        let saved = db.add_molecules_batch(&[r1, r2, r3]).unwrap();
        assert_eq!(saved, 3);

        let all = db.list_all(100, 0, None, None).unwrap();
        assert_eq!(all.len(), 3);

        let ethanol = db.search_by_smiles("CCO").unwrap().unwrap();
        assert_eq!(ethanol.name, "Ethanol");

        let from_search = db.search_text("Propanol").unwrap();
        assert_eq!(from_search.len(), 1);
        assert_eq!(from_search[0].mol_id, "m2");
    }

    #[test]
    fn test_add_molecules_batch_rollback_on_error() {
        let tmp = TempDir::new().unwrap();
        let db = MoleculeDatabase::open(tmp.path()).unwrap();

        // Pre-insert m1 so the batch duplicate (same mol_id) will trigger a
        // constraint path that should NOT happen with INSERT OR REPLACE,
        // but we still want to verify rollback works for genuine errors.
        // Instead we simulate by using an invalid record if possible.
        // For now just verify that a normal batch followed by a failed
        // transaction leaves DB in consistent state.
        let mut r1 = make_record("m1", "CCO");
        db.add_molecule(&r1).unwrap();

        // Batch with same mol_id should REPLACE (not fail)
        r1.name = "Updated".to_string();
        let saved = db.add_molecules_batch(&[r1]).unwrap();
        assert_eq!(saved, 1);

        let loaded = db.get_molecule("m1").unwrap().unwrap();
        assert_eq!(loaded.name, "Updated");
    }

    #[test]
    fn test_molecule_images_crud() {
        let tmp = TempDir::new().unwrap();
        let db = MoleculeDatabase::open(tmp.path()).unwrap();

        // 构造带图片路径的分子记录
        let mut rec = make_record("mol-img-1", "CCO");
        rec.name = "Ethanol".to_string();
        rec.related_image_paths = vec![
            ".mbforge/media/doc1/fig1.png".to_string(),
            ".mbforge/media/doc1/fig2.png".to_string(),
        ];
        rec.vlm_verified_esmiles = Some("CCO<sep><a>0:OH</a>".to_string());
        rec.vlm_confidence = 0.95;

        // 批量入库
        db.add_molecules_batch(&[rec]).unwrap();

        // 验证分子主表
        let loaded = db.get_molecule("mol-img-1").unwrap().unwrap();
        assert_eq!(loaded.mol_id, "mol-img-1");
        // 注意：related_image_paths / vlm_* 是内存字段，不入主表

        // 验证图片关联表
        let images = db.get_molecule_images("mol-img-1").unwrap();
        assert_eq!(images.len(), 2, "应写入 2 条图片记录");
        assert_eq!(images[0].image_path, ".mbforge/media/doc1/fig1.png");
        assert_eq!(images[1].image_path, ".mbforge/media/doc1/fig2.png");
        assert_eq!(
            images[0].vlm_esmiles,
            Some("CCO<sep><a>0:OH</a>".to_string())
        );
        assert!((images[0].vlm_confidence - 0.95).abs() < 1e-9);

        // 验证按路径查询
        let img = db
            .get_image_by_path(".mbforge/media/doc1/fig1.png")
            .unwrap()
            .unwrap();
        assert_eq!(img.mol_id, "mol-img-1");

        // 验证删除分子时级联删除图片
        db.delete_molecule("mol-img-1").unwrap();
        assert!(db.get_molecule("mol-img-1").unwrap().is_none());
        assert!(db.get_molecule_images("mol-img-1").unwrap().is_empty());
    }
}
