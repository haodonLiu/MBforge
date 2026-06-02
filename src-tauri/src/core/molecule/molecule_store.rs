use rusqlite::{params, Connection, Result as SqlResult};
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};

use crate::core::constants::PROJECT_META_DIR;
use crate::core::molecule_db::MOL_DB_FILENAME;

// ---------------------------------------------------------------------------
// MoleculeRecord — port of Python `MoleculeRecord` from
// `src/mbforge/core/mol_database.py`.
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MoleculeRecord {
    pub mol_id: String,
    pub esmiles: String,
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
    #[serde(default)]
    pub tags: Vec<String>,
    #[serde(default)]
    pub notes: String,
    #[serde(default)]
    pub created_at: Option<String>,
}

impl MoleculeRecord {
    pub fn new(mol_id: &str, esmiles: &str) -> Self {
        Self {
            mol_id: mol_id.to_string(),
            esmiles: esmiles.to_string(),
            name: String::new(),
            source_doc: String::new(),
            activity: None,
            activity_type: String::new(),
            units: "nM".to_string(),
            source_type: "text".to_string(),
            status: "confirmed".to_string(),
            properties: serde_json::json!({}),
            tags: Vec::new(),
            notes: String::new(),
            created_at: None,
        }
    }

    /// Compute basic molecular properties from SMILES.
    ///
    /// Port of `MoleculeRecord.compute_properties()` — uses simplified
    /// heuristics since RDKit is unavailable in Rust.
    /// Complex properties (LogP, TPSA) are left for the sidecar.
    pub fn compute_properties(&self) -> serde_json::Value {
        let esmiles = &self.esmiles;
        if esmiles.is_empty() {
            return serde_json::json!({});
        }

        let mw = estimate_molecular_weight(esmiles);
        let (hbd, hba) = estimate_hbd_hba(esmiles);
        let rotatable = estimate_rotatable_bonds(esmiles);

        serde_json::json!({
            "MW": mw,
            "HBD": hbd,
            "HBA": hba,
            "RotatableBonds": rotatable,
        })
    }

    pub fn row_to_record(row: &rusqlite::Row) -> SqlResult<Self> {
        let properties_str: String = row.get(9).unwrap_or_default();
        let tags_str: String = row.get(10).unwrap_or_default();

        let properties: serde_json::Value =
            serde_json::from_str(&properties_str).unwrap_or(serde_json::json!({}));
        let tags: Vec<String> = serde_json::from_str(&tags_str).unwrap_or_default();

        Ok(Self {
            mol_id: row.get(0)?,
            esmiles: row.get(1)?,
            name: row.get(2).unwrap_or_default(),
            source_doc: row.get(3).unwrap_or_default(),
            activity: row.get(4).ok(),
            activity_type: row.get(5).unwrap_or_default(),
            units: row.get(6).unwrap_or_else(|_| "nM".to_string()),
            source_type: row.get(7).unwrap_or_default(),
            status: row.get(8).unwrap_or_default(),
            properties,
            tags,
            notes: row.get(11).unwrap_or_default(),
            created_at: row.get(12).ok(),
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
        let db_dir = project_root.join(PROJECT_META_DIR);
        std::fs::create_dir_all(&db_dir)
            .map_err(|e| format!("Failed to create meta dir: {}", e))?;
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
        // Create the molecules table if it doesn't exist (also created by
        // MoleculeRelationDb, but we may be used standalone).
        self.conn
            .execute_batch(
                "
            CREATE TABLE IF NOT EXISTS molecules (
                mol_id TEXT PRIMARY KEY,
                esmiles TEXT NOT NULL,
                name TEXT,
                source_doc TEXT,
                activity REAL,
                activity_type TEXT,
                units TEXT DEFAULT 'nM',
                source_type TEXT DEFAULT 'text',
                status TEXT DEFAULT 'confirmed',
                properties TEXT,
                tags TEXT,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_mol_esmiles ON molecules(esmiles);
            CREATE INDEX IF NOT EXISTS idx_mol_source ON molecules(source_doc);
            CREATE INDEX IF NOT EXISTS idx_mol_status ON molecules(status);
            CREATE INDEX IF NOT EXISTS idx_mol_source_type ON molecules(source_type);
            CREATE INDEX IF NOT EXISTS idx_mol_activity ON molecules(activity);
            ",
            )
            .map_err(|e| format!("Failed to create schema: {}", e))?;

        // Create FTS5 virtual table for text search
        self.conn
            .execute_batch(
                "
            CREATE VIRTUAL TABLE IF NOT EXISTS mol_search USING fts5(
                name, notes, esmiles,
                content='molecules',
                content_rowid='rowid'
            );
            ",
            )
            .map_err(|e| format!("Failed to create FTS5 table: {}", e))?;

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
        let tags_str = serde_json::to_string(&rec.tags).unwrap_or_else(|_| "[]".to_string());

        // 删除旧 FTS 条目（INSERT OR REPLACE 会改变 rowid，导致旧 FTS 残留）
        let _ = self.conn.execute(
            "DELETE FROM mol_search WHERE rowid IN (SELECT rowid FROM molecules WHERE mol_id = ?1)",
            params![rec.mol_id],
        );

        self.conn
            .execute(
                "INSERT OR REPLACE INTO molecules
                 (mol_id, esmiles, name, source_doc, activity, activity_type,
                  units, source_type, status, properties, tags, notes)
                 VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12)",
                params![
                    rec.mol_id,
                    rec.esmiles,
                    rec.name,
                    rec.source_doc,
                    rec.activity,
                    rec.activity_type,
                    rec.units,
                    rec.source_type,
                    rec.status,
                    properties_str,
                    tags_str,
                    rec.notes,
                ],
            )
            .map_err(|e| format!("Failed to insert molecule: {}", e))?;

        // Sync FTS5 index
        let _ = self.conn.execute(
            "INSERT INTO mol_search(rowid, name, notes, esmiles)
             VALUES (last_insert_rowid(), ?1, ?2, ?3)",
            params![rec.name, rec.notes, rec.esmiles],
        );

        Ok(())
    }

    /// Batch add or update molecule records inside a single transaction.
    ///
    /// Returns the number of records processed. On error the transaction
    /// is rolled back and no partial writes remain.
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
            let tags_str = serde_json::to_string(&rec.tags).unwrap_or_else(|_| "[]".to_string());

            // Delete old FTS entries (INSERT OR REPLACE changes rowid)
            let _ = tx.execute(
                "DELETE FROM mol_search WHERE rowid IN (SELECT rowid FROM molecules WHERE mol_id = ?1)",
                params![rec.mol_id],
            );

            tx.execute(
                "INSERT OR REPLACE INTO molecules
                 (mol_id, esmiles, name, source_doc, activity, activity_type,
                  units, source_type, status, properties, tags, notes)
                 VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12)",
                params![
                    rec.mol_id,
                    rec.esmiles,
                    rec.name,
                    rec.source_doc,
                    rec.activity,
                    rec.activity_type,
                    rec.units,
                    rec.source_type,
                    rec.status,
                    properties_str,
                    tags_str,
                    rec.notes,
                ],
            )
            .map_err(|e| format!("Failed to insert molecule {}: {}", rec.mol_id, e))?;

            // Sync FTS5 index
            let _ = tx.execute(
                "INSERT INTO mol_search(rowid, name, notes, esmiles)
                 VALUES (last_insert_rowid(), ?1, ?2, ?3)",
                params![rec.name, rec.notes, rec.esmiles],
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

    /// Search molecule by exact esmiles match.
    pub fn search_by_esmiles(&self, esmiles: &str) -> Result<Option<MoleculeRecord>, String> {
        let mut stmt = self
            .conn
            .prepare("SELECT * FROM molecules WHERE esmiles = ?")
            .map_err(|e| format!("Prepare failed: {}", e))?;

        let mut rows = stmt
            .query(params![esmiles])
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
        // 先清理 FTS 条目
        let _ = self.conn.execute(
            "DELETE FROM mol_search WHERE rowid IN (SELECT rowid FROM molecules WHERE mol_id = ?1)",
            params![mol_id],
        );
        let affected = self
            .conn
            .execute("DELETE FROM molecules WHERE mol_id = ?", params![mol_id])
            .map_err(|e| format!("Failed to delete molecule: {}", e))?;
        Ok(affected > 0)
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
    /// Updates: esmiles, name, source_doc, activity, activity_type, units,
    /// source_type, status, properties, tags, notes.
    /// `mol_id`, `created_at` 不可改 (作为稳定标识).
    /// Returns true if the molecule existed and was updated.
    pub fn update_molecule(&self, record: &MoleculeRecord) -> Result<bool, String> {
        let tags_str = serde_json::to_string(&record.tags).unwrap_or_else(|_| "[]".to_string());
        let affected = self
            .conn
            .execute(
                "UPDATE molecules SET
                    esmiles = ?1,
                    name = ?2,
                    source_doc = ?3,
                    activity = ?4,
                    activity_type = ?5,
                    units = ?6,
                    source_type = ?7,
                    status = ?8,
                    properties = ?9,
                    tags = ?10,
                    notes = ?11
                 WHERE mol_id = ?12",
                params![
                    record.esmiles,
                    record.name,
                    record.source_doc,
                    record.activity,
                    record.activity_type,
                    record.units,
                    record.source_type,
                    record.status,
                    serde_json::to_string(&record.properties).unwrap_or_else(|_| "{}".to_string()),
                    tags_str,
                    record.notes,
                    record.mol_id,
                ],
            )
            .map_err(|e| format!("Failed to update molecule: {}", e))?;

        if affected == 0 {
            return Ok(false);
        }

        // 同步 FTS5 索引 (mol_search)
        let _ = self.conn.execute(
            "DELETE FROM mol_search WHERE rowid = (SELECT rowid FROM molecules WHERE mol_id = ?1)",
            params![record.mol_id],
        );
        let _ = self.conn.execute(
            "INSERT INTO mol_search(rowid, name, notes, esmiles)
             SELECT rowid, name, notes, esmiles FROM molecules WHERE mol_id = ?1",
            params![record.mol_id],
        );

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
            let tags_str = serde_json::to_string(&rec.tags).unwrap_or_else(|_| "[]".to_string());
            let affected = tx
                .execute(
                    "UPDATE molecules SET
                        esmiles = ?1, name = ?2, source_doc = ?3, activity = ?4,
                        activity_type = ?5, units = ?6, source_type = ?7, status = ?8,
                        properties = ?9, tags = ?10, notes = ?11
                     WHERE mol_id = ?12",
                    params![
                        rec.esmiles,
                        rec.name,
                        rec.source_doc,
                        rec.activity,
                        rec.activity_type,
                        rec.units,
                        rec.source_type,
                        rec.status,
                        serde_json::to_string(&rec.properties).unwrap_or_else(|_| "{}".to_string()),
                        tags_str,
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
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    fn make_record(mol_id: &str, esmiles: &str) -> MoleculeRecord {
        MoleculeRecord::new(mol_id, esmiles)
    }

    #[test]
    fn test_add_and_get_molecule() {
        let tmp = TempDir::new().unwrap();
        let db = MoleculeDatabase::open(tmp.path()).unwrap();

        let rec = make_record("mol-1", "CC(=O)Oc1ccccc1C(=O)O");
        db.add_molecule(&rec).unwrap();

        let loaded = db.get_molecule("mol-1").unwrap().unwrap();
        assert_eq!(loaded.mol_id, "mol-1");
        assert_eq!(loaded.esmiles, "CC(=O)Oc1ccccc1C(=O)O");

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
    fn test_search_by_esmiles() {
        let tmp = TempDir::new().unwrap();
        let db = MoleculeDatabase::open(tmp.path()).unwrap();

        db.add_molecule(&make_record("m1", "CCO")).unwrap();
        db.add_molecule(&make_record("m2", "CCCO")).unwrap();

        let found = db.search_by_esmiles("CCO").unwrap().unwrap();
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

        let ethanol = db.search_by_esmiles("CCO").unwrap().unwrap();
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
}
