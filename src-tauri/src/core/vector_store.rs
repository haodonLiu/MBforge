use std::path::Path;
use std::sync::Mutex;

use rusqlite::{params, Connection};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VectorItem {
    pub id: String,
    pub doc_id: String,
    pub text: String,
    pub embedding: Vec<f32>,
    pub metadata: serde_json::Value,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchResult {
    pub id: String,
    pub text: String,
    pub metadata: serde_json::Value,
    pub score: f32,
}

pub trait VectorStore: Send + Sync {
    fn upsert(&self, items: Vec<VectorItem>) -> Result<(), String>;
    fn search(
        &self,
        query_embedding: &[f32],
        top_k: usize,
        filter_doc_id: Option<&str>,
    ) -> Result<Vec<SearchResult>, String>;
    fn delete(&self, doc_id: &str) -> Result<(), String>;
    fn count(&self) -> Result<usize, String>;
}

pub struct SqliteVectorStore {
    conn: Mutex<Connection>,
}

impl SqliteVectorStore {
    pub fn new(db_path: &Path) -> Result<Self, String> {
        let conn = Connection::open(db_path)
            .map_err(|e| format!("Failed to open SQLite: {}", e))?;

        conn.execute(
            "CREATE TABLE IF NOT EXISTS sections (
                id TEXT PRIMARY KEY,
                doc_id TEXT NOT NULL,
                text TEXT NOT NULL,
                embedding BLOB NOT NULL,
                metadata TEXT NOT NULL
            )",
            [],
        )
        .map_err(|e| format!("Failed to create table: {}", e))?;

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_doc_id ON sections(doc_id)",
            [],
        )
        .map_err(|e| format!("Failed to create index: {}", e))?;

        Ok(Self { conn: Mutex::new(conn) })
    }

    fn serialize_embedding(emb: &[f32]) -> Vec<u8> {
        emb.iter().flat_map(|f| f.to_le_bytes()).collect()
    }

    fn deserialize_embedding(bytes: &[u8]) -> Vec<f32> {
        bytes
            .chunks_exact(4)
            .map(|chunk| {
                let arr: [u8; 4] = chunk.try_into().unwrap_or([0; 4]);
                f32::from_le_bytes(arr)
            })
            .collect()
    }
}

impl VectorStore for SqliteVectorStore {
    fn upsert(&self, items: Vec<VectorItem>) -> Result<(), String> {
        let conn = self.conn.lock().map_err(|e| format!("Lock error: {}", e))?;
        let tx = conn
            .unchecked_transaction()
            .map_err(|e| format!("Transaction failed: {}", e))?;

        for item in items {
            let emb_bytes = Self::serialize_embedding(&item.embedding);
            let meta_str = serde_json::to_string(&item.metadata)
                .map_err(|e| format!("Metadata serialize failed: {}", e))?;

            tx.execute(
                "INSERT OR REPLACE INTO sections (id, doc_id, text, embedding, metadata)
                 VALUES (?1, ?2, ?3, ?4, ?5)",
                params![item.id, item.doc_id, item.text, emb_bytes, meta_str],
            )
            .map_err(|e| format!("Upsert failed for {}: {}", item.id, e))?;
        }

        tx.commit()
            .map_err(|e| format!("Commit failed: {}", e))?;
        Ok(())
    }

    fn search(
        &self,
        query_embedding: &[f32],
        top_k: usize,
        filter_doc_id: Option<&str>,
    ) -> Result<Vec<SearchResult>, String> {
        let conn = self.conn.lock().map_err(|e| format!("Lock error: {}", e))?;

        let (sql, param) = if let Some(doc_id) = filter_doc_id {
            (
                "SELECT id, text, embedding, metadata FROM sections WHERE doc_id = ?1".to_string(),
                Some(doc_id.to_string()),
            )
        } else {
            (
                "SELECT id, text, embedding, metadata FROM sections".to_string(),
                None,
            )
        };

        let mut stmt = conn.prepare(&sql).map_err(|e| format!("Prepare failed: {}", e))?;

        let rows = if let Some(ref pid) = param {
            stmt.query_map([pid.as_str()], |row| {
                let id: String = row.get(0)?;
                let text: String = row.get(1)?;
                let emb_bytes: Vec<u8> = row.get(2)?;
                let meta_str: String = row.get(3)?;
                Ok((id, text, emb_bytes, meta_str))
            })
            .map_err(|e| format!("Query failed: {}", e))?
        } else {
            stmt.query_map([], |row| {
                let id: String = row.get(0)?;
                let text: String = row.get(1)?;
                let emb_bytes: Vec<u8> = row.get(2)?;
                let meta_str: String = row.get(3)?;
                Ok((id, text, emb_bytes, meta_str))
            })
            .map_err(|e| format!("Query failed: {}", e))?
        };

        let mut scored: Vec<(SearchResult, f32)> = Vec::new();
        for row in rows {
            let (id, text, emb_bytes, meta_str) =
                row.map_err(|e| format!("Row read failed: {}", e))?;
            let emb = Self::deserialize_embedding(&emb_bytes);
            let metadata: serde_json::Value =
                serde_json::from_str(&meta_str).unwrap_or(serde_json::json!({}));
            let score = cosine_similarity(query_embedding, &emb);
            scored.push((
                SearchResult {
                    id,
                    text,
                    metadata,
                    score,
                },
                score,
            ));
        }

        scored.sort_by(|a, b| {
            b.1.partial_cmp(&a.1)
                .unwrap_or(std::cmp::Ordering::Equal)
        });
        Ok(scored.into_iter().take(top_k).map(|(r, _)| r).collect())
    }

    fn delete(&self, doc_id: &str) -> Result<(), String> {
        let conn = self.conn.lock().map_err(|e| format!("Lock error: {}", e))?;
        conn.execute("DELETE FROM sections WHERE doc_id = ?1", [doc_id])
            .map_err(|e| format!("Delete failed: {}", e))?;
        Ok(())
    }

    fn count(&self) -> Result<usize, String> {
        let conn = self.conn.lock().map_err(|e| format!("Lock error: {}", e))?;
        let count: i64 = conn
            .query_row("SELECT COUNT(*) FROM sections", [], |row| row.get(0))
            .map_err(|e| format!("Count failed: {}", e))?;
        Ok(count as usize)
    }
}

fn cosine_similarity(a: &[f32], b: &[f32]) -> f32 {
    if a.len() != b.len() || a.is_empty() {
        return 0.0;
    }
    let mut dot = 0.0f32;
    let mut norm_a = 0.0f32;
    let mut norm_b = 0.0f32;
    for i in 0..a.len() {
        dot += a[i] * b[i];
        norm_a += a[i] * a[i];
        norm_b += b[i] * b[i];
    }
    if norm_a == 0.0 || norm_b == 0.0 {
        return 0.0;
    }
    dot / (norm_a.sqrt() * norm_b.sqrt())
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    #[test]
    fn test_sqlite_vector_store_roundtrip() {
        let tmp = TempDir::new().unwrap();
        let db_path = tmp.path().join("test.db");
        let store = SqliteVectorStore::new(&db_path).unwrap();

        let items = vec![VectorItem {
            id: "doc1_0".to_string(),
            doc_id: "doc1".to_string(),
            text: "hello world".to_string(),
            embedding: vec![1.0, 0.0, 0.0],
            metadata: serde_json::json!({"source": "test.pdf"}),
        }];
        store.upsert(items).unwrap();
        assert_eq!(store.count().unwrap(), 1);

        let results = store.search(&[1.0, 0.0, 0.0], 5, None).unwrap();
        assert_eq!(results.len(), 1);
        assert!(results[0].score > 0.99);
    }

    #[test]
    fn test_filter_by_doc_id() {
        let tmp = TempDir::new().unwrap();
        let db_path = tmp.path().join("test.db");
        let store = SqliteVectorStore::new(&db_path).unwrap();

        store
            .upsert(vec![
                VectorItem {
                    id: "doc1_0".to_string(),
                    doc_id: "doc1".to_string(),
                    text: "a".to_string(),
                    embedding: vec![1.0, 0.0, 0.0],
                    metadata: serde_json::json!({}),
                },
                VectorItem {
                    id: "doc2_0".to_string(),
                    doc_id: "doc2".to_string(),
                    text: "b".to_string(),
                    embedding: vec![0.0, 1.0, 0.0],
                    metadata: serde_json::json!({}),
                },
            ])
            .unwrap();

        let r = store.search(&[1.0, 0.0, 0.0], 5, Some("doc1")).unwrap();
        assert_eq!(r.len(), 1);
        assert_eq!(r[0].id, "doc1_0");
    }

    #[test]
    fn test_delete_by_doc_id() {
        let tmp = TempDir::new().unwrap();
        let db_path = tmp.path().join("test.db");
        let store = SqliteVectorStore::new(&db_path).unwrap();

        store
            .upsert(vec![VectorItem {
                id: "d1_0".to_string(),
                doc_id: "d1".to_string(),
                text: "x".to_string(),
                embedding: vec![1.0, 0.0],
                metadata: serde_json::json!({}),
            }])
            .unwrap();
        assert_eq!(store.count().unwrap(), 1);

        store.delete("d1").unwrap();
        assert_eq!(store.count().unwrap(), 0);
    }
}
