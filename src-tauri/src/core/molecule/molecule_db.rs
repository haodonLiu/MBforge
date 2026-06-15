#![allow(dead_code)]
use std::path::PathBuf;

use rusqlite::{params, Connection, Row};
use serde::{Deserialize, Serialize};
use serde_json::Value as JsonValue;
use tokio::sync::Mutex;

use crate::core::constants::INDEX_DIR;
pub const MOL_RELATIONS_TABLE: &str = "molecule_relations";
pub const MOL_DETECTIONS_TABLE: &str = "molecule_detections";
pub const MOL_DB_FILENAME: &str = "molecules.db";

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum RelationType {
    Similar,
    SameAs,
    Scaffold,
    Cluster,
}

impl RelationType {
    pub fn as_str(&self) -> &'static str {
        match self {
            RelationType::Similar => "similar",
            RelationType::SameAs => "same_as",
            RelationType::Scaffold => "scaffold",
            RelationType::Cluster => "cluster",
        }
    }

    pub fn from_str(s: &str) -> Option<Self> {
        match s {
            "similar" => Some(RelationType::Similar),
            "same_as" => Some(RelationType::SameAs),
            "scaffold" => Some(RelationType::Scaffold),
            "cluster" => Some(RelationType::Cluster),
            _ => None,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MoleculeRelation {
    pub id: Option<i64>,
    pub mol_a_id: String,
    pub mol_b_id: String,
    pub relation_type: RelationType,
    pub score: Option<f64>,
    pub metadata: Option<JsonValue>,
    pub created_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RelationStats {
    pub total: i64,
    pub similar: i64,
    pub same_as: i64,
    pub scaffold: i64,
    pub cluster: i64,
}

pub struct MoleculeRelationDb {
    db_path: PathBuf,
    conn: Mutex<Connection>,
}

/// One row of `molecule_detections` — links a molecule (in `molecules`)
/// to a specific PDF page detection. `molecule_detections` is a join table
/// that the PdfViewer uses to render bbox overlays on a known page.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MoleculeDetectionRow {
    pub mol_id: String,
    pub doc_id: String,
    pub page: usize,
    pub bbox: [f64; 4],
    pub crop_relpath: Option<String>,
    pub conf_moldet: Option<f64>,
    pub conf_molscribe: Option<f64>,
    pub vlm_verified_esmiles: Option<String>,
    pub vlm_confidence: Option<f64>,
}

impl MoleculeRelationDb {
    pub async fn new(project_root: &std::path::Path) -> Result<Self, String> {
        let db_dir = project_root.join(INDEX_DIR);
        std::fs::create_dir_all(&db_dir)
            .map_err(|e| format!("Failed to create index dir: {}", e))?;
        let db_path = db_dir.join(MOL_DB_FILENAME);

        let conn = Connection::open(&db_path)
            .map_err(|e| format!("Failed to open db {}: {}", db_path.display(), e))?;

        let db = Self {
            db_path,
            conn: Mutex::new(conn),
        };
        db.init_schema().await?;
        Ok(db)
    }

    async fn init_schema(&self) -> Result<(), String> {
        let conn = self.conn.lock().await;
        conn.execute_batch("PRAGMA foreign_keys = ON;")
            .map_err(|e| format!("Failed to enable foreign_keys: {}", e))?;

        // 只创建 relations 表。molecules 表由 molecule_store.rs 负责。
        let sql = format!(
            r#"
            CREATE TABLE IF NOT EXISTS {} (
                id INTEGER PRIMARY KEY,
                mol_a_id TEXT NOT NULL,
                mol_b_id TEXT NOT NULL,
                relation_type TEXT NOT NULL CHECK(relation_type IN ('similar','same_as','scaffold','cluster')),
                score REAL,
                metadata TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(mol_a_id, mol_b_id, relation_type)
            );
            CREATE INDEX IF NOT EXISTS idx_relations_type ON {}(relation_type);
            CREATE INDEX IF NOT EXISTS idx_relations_a ON {}(mol_a_id);
            CREATE INDEX IF NOT EXISTS idx_relations_b ON {}(mol_b_id);
            "#,
            MOL_RELATIONS_TABLE, MOL_RELATIONS_TABLE, MOL_RELATIONS_TABLE, MOL_RELATIONS_TABLE
        );

        conn.execute_batch(&sql)
            .map_err(|e| format!("Failed to create schema: {}", e))?;

        // molecule_detections：每个分子在 PDF 哪一页哪个位置被检测到。
        // 这是 DetectionCache（per-page JSON）的关系镜像 —— JSON 是
        // 完整原始结果，这个表只存关键索引供 SQL 查询（"在所有 PDF
        // 里找这个分子 / 这页有哪些分子"）。
        //
        // 设计：UNIQUE(mol_id, doc_id, page) 保证同一分子在同一 PDF
        // 同一页只存一次（重复检测时 UPSERT）。
        let det_sql = format!(
            r#"
            CREATE TABLE IF NOT EXISTS {} (
                id INTEGER PRIMARY KEY,
                mol_id TEXT NOT NULL,
                doc_id TEXT NOT NULL,
                page INTEGER NOT NULL,
                bbox_x0 REAL NOT NULL,
                bbox_y0 REAL NOT NULL,
                bbox_x1 REAL NOT NULL,
                bbox_y1 REAL NOT NULL,
                crop_relpath TEXT,
                conf_moldet REAL,
                conf_molscribe REAL,
                vlm_verified_esmiles TEXT,
                vlm_confidence REAL,
                detected_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(mol_id, doc_id, page)
            );
            CREATE INDEX IF NOT EXISTS idx_detect_doc_page ON {}(doc_id, page);
            CREATE INDEX IF NOT EXISTS idx_detect_mol ON {}(mol_id);
            "#,
            MOL_DETECTIONS_TABLE, MOL_DETECTIONS_TABLE, MOL_DETECTIONS_TABLE
        );
        conn.execute_batch(&det_sql)
            .map_err(|e| format!("Failed to create detections schema: {}", e))?;

        Ok(())
    }

    pub async fn add_relation(&self, rel: &MoleculeRelation) -> Result<i64, String> {
        let conn = self.conn.lock().await;
        let metadata_json = rel
            .metadata
            .as_ref()
            .map(|m| serde_json::to_string(m).unwrap_or_default());
        let now = super::super::helpers::now_rfc3339();

        conn.execute(
            &format!(
                r#"INSERT OR REPLACE INTO {} (mol_a_id, mol_b_id, relation_type, score, metadata, created_at)
                   VALUES (?1, ?2, ?3, ?4, ?5, ?6)"#,
                MOL_RELATIONS_TABLE
            ),
            params![
                &rel.mol_a_id,
                &rel.mol_b_id,
                rel.relation_type.as_str(),
                rel.score,
                metadata_json.as_deref(),
                &now,
            ],
        )
        .map_err(|e| format!("Failed to insert relation: {}", e))?;

        Ok(conn.last_insert_rowid())
    }

    pub async fn delete_relation(&self, id: i64) -> Result<bool, String> {
        let conn = self.conn.lock().await;
        let affected = conn
            .execute("DELETE FROM molecule_relations WHERE id = ?", params![id])
            .map_err(|e| format!("Failed to delete relation {}: {}", id, e))?;
        Ok(affected > 0)
    }

    pub async fn get_relation(&self, id: i64) -> Result<Option<MoleculeRelation>, String> {
        let conn = self.conn.lock().await;
        let mut stmt = conn
            .prepare("SELECT * FROM molecule_relations WHERE id = ?")
            .map_err(|e| format!("Prepare failed: {}", e))?;
        let mut rows = stmt
            .query(params![id])
            .map_err(|e| format!("Query failed: {}", e))?;

        if let Some(row) = rows
            .next()
            .map_err(|e| format!("Row fetch failed: {}", e))?
        {
            Ok(Some(self.row_to_relation(row)?))
        } else {
            Ok(None)
        }
    }

    pub async fn find_by_molecule(&self, mol_id: &str) -> Result<Vec<MoleculeRelation>, String> {
        let conn = self.conn.lock().await;
        let mut stmt = conn
            .prepare(
                "SELECT * FROM molecule_relations
                 WHERE mol_a_id = ? OR mol_b_id = ?
                 ORDER BY created_at DESC",
            )
            .map_err(|e| format!("Prepare failed: {}", e))?;
        let mut rows = stmt
            .query(params![mol_id, mol_id])
            .map_err(|e| format!("Query failed: {}", e))?;

        let mut results = Vec::new();
        while let Some(row) = rows
            .next()
            .map_err(|e| format!("Row fetch failed: {}", e))?
        {
            results.push(self.row_to_relation(row)?);
        }
        Ok(results)
    }

    pub async fn find_similar(
        &self,
        mol_id: &str,
        min_score: f64,
    ) -> Result<Vec<(MoleculeRelation, f64)>, String> {
        let conn = self.conn.lock().await;
        let mut stmt = conn
            .prepare(
                "SELECT * FROM molecule_relations
                 WHERE relation_type = 'similar'
                   AND score >= ?1
                   AND (mol_a_id = ?2 OR mol_b_id = ?3)
                 ORDER BY score DESC",
            )
            .map_err(|e| format!("Prepare failed: {}", e))?;
        let mut rows = stmt
            .query(params![min_score, mol_id, mol_id])
            .map_err(|e| format!("Query failed: {}", e))?;

        let mut results = Vec::new();
        while let Some(row) = rows
            .next()
            .map_err(|e| format!("Row fetch failed: {}", e))?
        {
            let rel = self.row_to_relation(row)?;
            if let Some(score) = rel.score {
                results.push((rel, score));
            }
        }
        Ok(results)
    }

    pub async fn find_same_as(&self, mol_id: &str) -> Result<Vec<MoleculeRelation>, String> {
        let conn = self.conn.lock().await;
        let mut stmt = conn
            .prepare(
                "SELECT * FROM molecule_relations
                 WHERE relation_type = 'same_as'
                   AND (mol_a_id = ?1 OR mol_b_id = ?2)
                 ORDER BY score DESC",
            )
            .map_err(|e| format!("Prepare failed: {}", e))?;
        let mut rows = stmt
            .query(params![mol_id, mol_id])
            .map_err(|e| format!("Query failed: {}", e))?;

        let mut results = Vec::new();
        while let Some(row) = rows
            .next()
            .map_err(|e| format!("Row fetch failed: {}", e))?
        {
            results.push(self.row_to_relation(row)?);
        }
        Ok(results)
    }

    pub async fn relations_conn(&self) -> tokio::sync::MutexGuard<'_, Connection> {
        self.conn.lock().await
    }

    pub fn molecules_conn(&self) -> Result<Connection, String> {
        Connection::open(&self.db_path).map_err(|e| format!("Failed to open molecules db: {}", e))
    }

    pub async fn get_stats(&self) -> Result<RelationStats, String> {
        let conn = self.conn.lock().await;
        let total: i64 = conn
            .query_row("SELECT COUNT(*) FROM molecule_relations", [], |r| r.get(0))
            .unwrap_or(0);
        let similar: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM molecule_relations WHERE relation_type = 'similar'",
                [],
                |r| r.get(0),
            )
            .unwrap_or(0);
        let same_as: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM molecule_relations WHERE relation_type = 'same_as'",
                [],
                |r| r.get(0),
            )
            .unwrap_or(0);
        let scaffold: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM molecule_relations WHERE relation_type = 'scaffold'",
                [],
                |r| r.get(0),
            )
            .unwrap_or(0);
        let cluster: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM molecule_relations WHERE relation_type = 'cluster'",
                [],
                |r| r.get(0),
            )
            .unwrap_or(0);
        Ok(RelationStats {
            total,
            similar,
            same_as,
            scaffold,
            cluster,
        })
    }

    fn row_to_relation(&self, row: &Row) -> Result<MoleculeRelation, String> {
        let rel_type_str: String = row.get(3).unwrap_or_default();
        let metadata_str: Option<String> = row.get(5).ok();
        let metadata: Option<JsonValue> = metadata_str.and_then(|s| serde_json::from_str(&s).ok());

        Ok(MoleculeRelation {
            id: row.get(0).ok(),
            mol_a_id: row.get(1).unwrap_or_default(),
            mol_b_id: row.get(2).unwrap_or_default(),
            relation_type: RelationType::from_str(&rel_type_str).unwrap_or(RelationType::Similar),
            score: row.get(4).ok(),
            metadata,
            created_at: row.get(6).unwrap_or_default(),
        })
    }

    /// Insert or update a detection record. `INSERT OR REPLACE` is safe
    /// because `UNIQUE(mol_id, doc_id, page)` guarantees idempotency.
    pub async fn upsert_detection(&self, row: &MoleculeDetectionRow) -> Result<(), String> {
        let conn = self.conn.lock().await;
        let sql = format!(
            r#"INSERT OR REPLACE INTO {}
               (mol_id, doc_id, page, bbox_x0, bbox_y0, bbox_x1, bbox_y1,
                crop_relpath, conf_moldet, conf_molscribe,
                vlm_verified_esmiles, vlm_confidence)
               VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12)"#,
            MOL_DETECTIONS_TABLE
        );
        conn.execute(
            &sql,
            params![
                row.mol_id,
                row.doc_id,
                row.page as i64,
                row.bbox[0],
                row.bbox[1],
                row.bbox[2],
                row.bbox[3],
                row.crop_relpath,
                row.conf_moldet,
                row.conf_molscribe,
                row.vlm_verified_esmiles,
                row.vlm_confidence,
            ],
        )
        .map_err(|e| format!("Failed to upsert detection: {}", e))?;
        Ok(())
    }

    /// All detections for a single PDF page (used by PdfViewer when
    /// rendering bbox overlays).
    pub async fn detections_for_page(
        &self,
        doc_id: &str,
        page: usize,
    ) -> Result<Vec<MoleculeDetectionRow>, String> {
        let conn = self.conn.lock().await;
        let mut stmt = conn
            .prepare(&format!(
                "SELECT mol_id, doc_id, page, bbox_x0, bbox_y0, bbox_x1, bbox_y1,
                        crop_relpath, conf_moldet, conf_molscribe,
                        vlm_verified_esmiles, vlm_confidence
                 FROM {} WHERE doc_id = ?1 AND page = ?2",
                MOL_DETECTIONS_TABLE
            ))
            .map_err(|e| format!("Prepare failed: {}", e))?;
        let rows = stmt
            .query_map(params![doc_id, page as i64], |row| {
                Ok(MoleculeDetectionRow {
                    mol_id: row.get(0)?,
                    doc_id: row.get(1)?,
                    page: row.get::<_, i64>(2)? as usize,
                    bbox: [row.get(3)?, row.get(4)?, row.get(5)?, row.get(6)?],
                    crop_relpath: row.get(7)?,
                    conf_moldet: row.get(8)?,
                    conf_molscribe: row.get(9)?,
                    vlm_verified_esmiles: row.get(10)?,
                    vlm_confidence: row.get(11)?,
                })
            })
            .map_err(|e| format!("Query failed: {}", e))?;
        rows.collect::<Result<Vec<_>, _>>()
            .map_err(|e| format!("Row fetch failed: {}", e))
    }

    /// All pages in a document that have at least one detection.
    pub async fn detected_pages_for_doc(&self, doc_id: &str) -> Result<Vec<usize>, String> {
        let conn = self.conn.lock().await;
        let mut stmt = conn
            .prepare(&format!(
                "SELECT DISTINCT page FROM {} WHERE doc_id = ?1 ORDER BY page",
                MOL_DETECTIONS_TABLE
            ))
            .map_err(|e| format!("Prepare failed: {}", e))?;
        let rows = stmt
            .query_map(params![doc_id], |row| row.get::<_, i64>(0))
            .map_err(|e| format!("Query failed: {}", e))?;
        rows.map(|r| r.map(|n| n as usize))
            .collect::<Result<Vec<_>, _>>()
            .map_err(|e| format!("Row fetch failed: {}", e))
    }

    /// All documents/places a given molecule was detected in.
    pub async fn detection_locations_for_mol(
        &self,
        mol_id: &str,
    ) -> Result<Vec<(String, usize)>, String> {
        let conn = self.conn.lock().await;
        let mut stmt = conn
            .prepare(&format!(
                "SELECT doc_id, page FROM {} WHERE mol_id = ?1 ORDER BY detected_at DESC",
                MOL_DETECTIONS_TABLE
            ))
            .map_err(|e| format!("Prepare failed: {}", e))?;
        let rows = stmt
            .query_map(params![mol_id], |row| {
                Ok((row.get::<_, String>(0)?, row.get::<_, i64>(1)? as usize))
            })
            .map_err(|e| format!("Query failed: {}", e))?;
        rows.collect::<Result<Vec<_>, _>>()
            .map_err(|e| format!("Row fetch failed: {}", e))
    }

    /// Delete all detections for one document (called when a doc is removed
    /// from the project, or when the PDF hash changes).
    pub async fn delete_detections_for_doc(&self, doc_id: &str) -> Result<usize, String> {
        let conn = self.conn.lock().await;
        let n = conn
            .execute(
                &format!("DELETE FROM {} WHERE doc_id = ?1", MOL_DETECTIONS_TABLE),
                params![doc_id],
            )
            .map_err(|e| format!("Failed to delete detections: {}", e))?;
        Ok(n)
    }
}
