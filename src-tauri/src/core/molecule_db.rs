use rusqlite::{params, Connection, Row};
use serde::{Deserialize, Serialize};
use serde_json::Value as JsonValue;
use std::path::PathBuf;
use std::sync::Mutex;

use crate::core::constants::PROJECT_META_DIR;

pub const MOL_RELATIONS_TABLE: &str = "molecule_relations";
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

impl MoleculeRelationDb {
    pub fn new(project_root: &std::path::Path) -> Result<Self, String> {
        let db_dir = project_root.join(PROJECT_META_DIR);
        std::fs::create_dir_all(&db_dir)
            .map_err(|e| format!("Failed to create meta dir: {}", e))?;
        let db_path = db_dir.join(MOL_DB_FILENAME);

        let conn = Connection::open(&db_path)
            .map_err(|e| format!("Failed to open db {}: {}", db_path.display(), e))?;

        let db = Self {
            db_path,
            conn: Mutex::new(conn),
        };
        db.init_schema()?;
        Ok(db)
    }

    fn init_schema(&self) -> Result<(), String> {
        let conn = self.conn.lock().unwrap();
        conn.execute_batch("PRAGMA foreign_keys = ON;")
            .map_err(|e| format!("Failed to enable foreign_keys: {}", e))?;

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
            CREATE INDEX IF NOT EXISTS idx_mol_activity ON molecules(activity);
            "#,
            MOL_RELATIONS_TABLE,
            MOL_RELATIONS_TABLE,
            MOL_RELATIONS_TABLE,
            MOL_RELATIONS_TABLE
        );

        conn.execute_batch(&sql)
            .map_err(|e| format!("Failed to create schema: {}", e))?;
        Ok(())
    }

    pub fn add_relation(&self, rel: &MoleculeRelation) -> Result<i64, String> {
        let conn = self.conn.lock().unwrap();
        let metadata_json = rel
            .metadata
            .as_ref()
            .map(|m| serde_json::to_string(m).unwrap_or_default());
        let now = chrono::Utc::now().to_rfc3339();

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

    pub fn delete_relation(&self, id: i64) -> Result<bool, String> {
        let conn = self.conn.lock().unwrap();
        let affected = conn
            .execute("DELETE FROM molecule_relations WHERE id = ?", params![id])
            .map_err(|e| format!("Failed to delete relation {}: {}", id, e))?;
        Ok(affected > 0)
    }

    pub fn get_relation(&self, id: i64) -> Result<Option<MoleculeRelation>, String> {
        let conn = self.conn.lock().unwrap();
        let mut stmt = conn
            .prepare("SELECT * FROM molecule_relations WHERE id = ?")
            .map_err(|e| format!("Prepare failed: {}", e))?;
        let mut rows = stmt
            .query(params![id])
            .map_err(|e| format!("Query failed: {}", e))?;

        if let Some(row) = rows.next().map_err(|e| format!("Row fetch failed: {}", e))? {
            Ok(Some(self.row_to_relation(row)?))
        } else {
            Ok(None)
        }
    }

    pub fn find_by_molecule(&self, mol_id: &str) -> Result<Vec<MoleculeRelation>, String> {
        let conn = self.conn.lock().unwrap();
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
        while let Some(row) = rows.next().map_err(|e| format!("Row fetch failed: {}", e))? {
            results.push(self.row_to_relation(row)?);
        }
        Ok(results)
    }

    pub fn find_similar(
        &self,
        mol_id: &str,
        min_score: f64,
    ) -> Result<Vec<(MoleculeRelation, f64)>, String> {
        let conn = self.conn.lock().unwrap();
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
        while let Some(row) = rows.next().map_err(|e| format!("Row fetch failed: {}", e))? {
            let rel = self.row_to_relation(row)?;
            if let Some(score) = rel.score {
                results.push((rel, score));
            }
        }
        Ok(results)
    }

    pub fn find_same_as(&self, mol_id: &str) -> Result<Vec<MoleculeRelation>, String> {
        let conn = self.conn.lock().unwrap();
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
        while let Some(row) = rows.next().map_err(|e| format!("Row fetch failed: {}", e))? {
            results.push(self.row_to_relation(row)?);
        }
        Ok(results)
    }

    pub fn relations_conn(&self) -> std::sync::MutexGuard<'_, Connection> {
        self.conn.lock().unwrap()
    }

    pub fn molecules_conn(&self) -> Result<Connection, String> {
        Connection::open(&self.db_path)
            .map_err(|e| format!("Failed to open molecules db: {}", e))
    }

    pub fn get_stats(&self) -> Result<RelationStats, String> {
        let conn = self.conn.lock().unwrap();
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
        let metadata: Option<JsonValue> = metadata_str
            .and_then(|s| serde_json::from_str(&s).ok());

        Ok(MoleculeRelation {
            id: row.get(0).ok(),
            mol_a_id: row.get(1).unwrap_or_default(),
            mol_b_id: row.get(2).unwrap_or_default(),
            relation_type: RelationType::from_str(&rel_type_str)
                .unwrap_or(RelationType::Similar),
            score: row.get(4).ok(),
            metadata,
            created_at: row.get(6).unwrap_or_default(),
        })
    }
}
