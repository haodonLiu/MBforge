//! 知识库存储 — FTS5 全文搜索（无需 embedding 模型）
//!
//! 使用 SQLite FTS5 虚拟表实现文本搜索，替代向量相似度搜索。
//! 不依赖任何 embedding 模型，纯本地运行。

use std::path::Path;
use std::sync::Mutex;

use rusqlite::{params, Connection};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VectorItem {
    pub id: String,
    pub doc_id: String,
    pub text: String,
    pub embedding: Vec<f32>,  // 保留字段，FTS5 不使用
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
        query: &str,
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

        // 主表：存储文本和元数据
        conn.execute(
            "CREATE TABLE IF NOT EXISTS sections (
                id TEXT PRIMARY KEY,
                doc_id TEXT NOT NULL,
                text TEXT NOT NULL,
                metadata TEXT NOT NULL
            )",
            [],
        )
        .map_err(|e| format!("Failed to create table: {}", e))?;

        // FTS5 虚拟表：用于全文搜索
        conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS sections_fts USING fts5(
                id, text, content='sections', content_rowid='rowid'
            )",
            [],
        )
        .map_err(|e| format!("Failed to create FTS5 table: {}", e))?;

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_doc_id ON sections(doc_id)",
            [],
        )
        .map_err(|e| format!("Failed to create index: {}", e))?;

        Ok(Self { conn: Mutex::new(conn) })
    }
}

impl VectorStore for SqliteVectorStore {
    fn upsert(&self, items: Vec<VectorItem>) -> Result<(), String> {
        let conn = self.conn.lock().map_err(|e| format!("Lock error: {}", e))?;
        let tx = conn
            .unchecked_transaction()
            .map_err(|e| format!("Transaction failed: {}", e))?;

        for item in items {
            let meta_str = serde_json::to_string(&item.metadata)
                .map_err(|e| format!("Metadata serialize failed: {}", e))?;

            // 插入主表
            tx.execute(
                "INSERT OR REPLACE INTO sections (id, doc_id, text, metadata)
                 VALUES (?1, ?2, ?3, ?4)",
                params![item.id, item.doc_id, item.text, meta_str],
            )
            .map_err(|e| format!("Upsert failed for {}: {}", item.id, e))?;

            // 同步到 FTS5 索引
            tx.execute(
                "DELETE FROM sections_fts WHERE id = ?1",
                params![item.id],
            ).ok(); // 忽略删除错误（可能是新条目）

            tx.execute(
                "INSERT INTO sections_fts (id, text) VALUES (?1, ?2)",
                params![item.id, item.text],
            )
            .map_err(|e| format!("FTS5 insert failed for {}: {}", item.id, e))?;
        }

        tx.commit()
            .map_err(|e| format!("Commit failed: {}", e))?;
        Ok(())
    }

    fn search(
        &self,
        query: &str,
        top_k: usize,
        filter_doc_id: Option<&str>,
    ) -> Result<Vec<SearchResult>, String> {
        let conn = self.conn.lock().map_err(|e| format!("Lock error: {}", e))?;

        // 对查询文本进行清理，移除 FTS5 特殊字符
        let clean_query = query
            .replace('"', "")
            .replace("'", "")
            .replace('-', " ")
            .split_whitespace()
            .filter(|w| w.len() >= 2)
            .collect::<Vec<_>>()
            .join(" OR ");

        if clean_query.is_empty() {
            // 空查询：返回最近的文档
            let sql = if filter_doc_id.is_some() {
                "SELECT s.id, s.text, s.metadata FROM sections s WHERE s.doc_id = ?1 ORDER BY s.rowid DESC LIMIT ?2"
            } else {
                "SELECT s.id, s.text, s.metadata FROM sections s ORDER BY s.rowid DESC LIMIT ?1"
            };

            let mut stmt = conn.prepare(sql).map_err(|e| format!("Prepare failed: {}", e))?;

            let row_mapper = |row: &rusqlite::Row| -> Result<(String, String, String), rusqlite::Error> {
                Ok((row.get(0)?, row.get(1)?, row.get(2)?))
            };

            let rows = if let Some(doc_id) = filter_doc_id {
                stmt.query_map(params![doc_id, top_k], row_mapper)
            } else {
                stmt.query_map(params![top_k], row_mapper)
            }.map_err(|e| format!("Query failed: {}", e))?;

            let mut results = Vec::new();
            for row in rows {
                let (id, text, meta_str) = row.map_err(|e| format!("Row error: {}", e))?;
                let metadata: serde_json::Value =
                    serde_json::from_str(&meta_str).unwrap_or(serde_json::json!({}));
                results.push(SearchResult { id, text, metadata, score: 1.0 });
            }
            return Ok(results);
        }

        // FTS5 搜索
        let (sql, params_vec): (String, Vec<Box<dyn rusqlite::types::ToSql>>) = if let Some(doc_id) = filter_doc_id {
            (
                "SELECT s.id, s.text, s.metadata, rank
                 FROM sections_fts f
                 JOIN sections s ON f.id = s.id
                 WHERE sections_fts MATCH ?1 AND s.doc_id = ?2
                 ORDER BY rank
                 LIMIT ?3".into(),
                vec![
                    Box::new(clean_query) as Box<dyn rusqlite::types::ToSql>,
                    Box::new(doc_id.to_string()),
                    Box::new(top_k as i64),
                ],
            )
        } else {
            (
                "SELECT s.id, s.text, s.metadata, rank
                 FROM sections_fts f
                 JOIN sections s ON f.id = s.id
                 WHERE sections_fts MATCH ?1
                 ORDER BY rank
                 LIMIT ?2".into(),
                vec![
                    Box::new(clean_query) as Box<dyn rusqlite::types::ToSql>,
                    Box::new(top_k as i64),
                ],
            )
        };

        let mut stmt = conn.prepare(&sql).map_err(|e| format!("Prepare failed: {}", e))?;
        let param_refs: Vec<&dyn rusqlite::types::ToSql> = params_vec.iter().map(|p| p.as_ref()).collect();

        let rows = stmt
            .query_map(param_refs.as_slice(), |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, String>(1)?,
                    row.get::<_, String>(2)?,
                    row.get::<_, f64>(3).unwrap_or(0.0),
                ))
            })
            .map_err(|e| format!("Query failed: {}", e))?;

        let mut results = Vec::new();
        for row in rows {
            let (id, text, meta_str, rank) = row.map_err(|e| format!("Row error: {}", e))?;
            let metadata: serde_json::Value =
                serde_json::from_str(&meta_str).unwrap_or(serde_json::json!({}));
            // FTS5 rank 是负数，越小越好，转换为 0-1 分数
            let score: f32 = if rank < 0.0 {
                (1.0f32 / (1.0f32 + rank.abs() as f32))
            } else {
                0.5f32
            };
            results.push(SearchResult {
                id,
                text,
                metadata,
                score,
            });
        }

        Ok(results)
    }

    fn delete(&self, doc_id: &str) -> Result<(), String> {
        let conn = self.conn.lock().map_err(|e| format!("Lock error: {}", e))?;
        // 先从 FTS5 删除
        conn.execute(
            "DELETE FROM sections_fts WHERE id IN (SELECT id FROM sections WHERE doc_id = ?1)",
            [doc_id],
        ).ok();
        // 再从主表删除
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_fts5_store() {
        let dir = tempfile::tempdir().unwrap();
        let db_path = dir.path().join("test.db");
        let store = SqliteVectorStore::new(&db_path).unwrap();

        let items = vec![
            VectorItem {
                id: "1".into(),
                doc_id: "doc1".into(),
                text: "aspirin is a pain reliever".into(),
                embedding: vec![],
                metadata: serde_json::json!({"title": "Aspirin"}),
            },
            VectorItem {
                id: "2".into(),
                doc_id: "doc1".into(),
                text: "ibuprofen is an anti-inflammatory".into(),
                embedding: vec![],
                metadata: serde_json::json!({"title": "Ibuprofen"}),
            },
        ];

        store.upsert(items).unwrap();
        assert_eq!(store.count().unwrap(), 2);

        let results = store.search("aspirin", 10, None).unwrap();
        assert!(!results.is_empty());
        assert!(results[0].text.contains("aspirin"));
    }
}
