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
    pub embedding: Vec<f32>, // 保留字段，FTS5 不使用
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
        let conn =
            Connection::open(db_path).map_err(|e| format!("Failed to open SQLite: {}", e))?;

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

        // 旧版 v0 schema 包含 `embedding BLOB NOT NULL` 列，写入路径不再维护该列，
        // 直接 DROP COLUMN 升级到当前 FTS5-only schema（幂等执行）。
        migrate_legacy_schema(&conn)?;

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

        Ok(Self {
            conn: Mutex::new(conn),
        })
    }
}

/// 将旧版 v0 schema（含 `embedding` 列）迁移到当前 FTS5-only schema。
///
/// 通过 `PRAGMA table_info` 检测列名，若发现遗留的 `embedding` 列则执行
/// `ALTER TABLE ... DROP COLUMN`。SQLite 3.35+ 支持 DROP COLUMN，
/// `rusqlite` 的 `bundled` feature 自带 3.46+，无需额外检查版本。
fn migrate_legacy_schema(conn: &Connection) -> Result<(), String> {
    let mut stmt = conn
        .prepare("PRAGMA table_info(sections)")
        .map_err(|e| format!("Prepare PRAGMA failed: {}", e))?;
    let column_names: Vec<String> = stmt
        .query_map([], |row| row.get::<_, String>(1))
        .map_err(|e| format!("Query PRAGMA failed: {}", e))?
        .filter_map(|r| r.ok())
        .collect();

    if column_names.iter().any(|name| name == "embedding") {
        log::info!("vector_store: dropping legacy `embedding` column from sections");
        conn.execute("ALTER TABLE sections DROP COLUMN embedding", [])
            .map_err(|e| format!("DROP COLUMN failed: {}", e))?;
    }
    Ok(())
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
            tx.execute("DELETE FROM sections_fts WHERE id = ?1", params![item.id])
                .ok(); // 忽略删除错误（可能是新条目）

            tx.execute(
                "INSERT INTO sections_fts (id, text) VALUES (?1, ?2)",
                params![item.id, item.text],
            )
            .map_err(|e| format!("FTS5 insert failed for {}: {}", item.id, e))?;
        }

        tx.commit().map_err(|e| format!("Commit failed: {}", e))?;
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

            let mut stmt = conn
                .prepare(sql)
                .map_err(|e| format!("Prepare failed: {}", e))?;

            let row_mapper =
                |row: &rusqlite::Row| -> Result<(String, String, String), rusqlite::Error> {
                    Ok((row.get(0)?, row.get(1)?, row.get(2)?))
                };

            let rows = if let Some(doc_id) = filter_doc_id {
                stmt.query_map(params![doc_id, top_k], row_mapper)
            } else {
                stmt.query_map(params![top_k], row_mapper)
            }
            .map_err(|e| format!("Query failed: {}", e))?;

            let mut results = Vec::new();
            for row in rows {
                let (id, text, meta_str) = row.map_err(|e| format!("Row error: {}", e))?;
                let metadata: serde_json::Value =
                    serde_json::from_str(&meta_str).unwrap_or(serde_json::json!({}));
                results.push(SearchResult {
                    id,
                    text,
                    metadata,
                    score: 1.0,
                });
            }
            return Ok(results);
        }

        // FTS5 搜索
        let (sql, params_vec): (String, Vec<Box<dyn rusqlite::types::ToSql>>) =
            if let Some(doc_id) = filter_doc_id {
                (
                    "SELECT s.id, s.text, s.metadata, rank
                 FROM sections_fts f
                 JOIN sections s ON f.id = s.id
                 WHERE sections_fts MATCH ?1 AND s.doc_id = ?2
                 ORDER BY rank
                 LIMIT ?3"
                        .into(),
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
                 LIMIT ?2"
                        .into(),
                    vec![
                        Box::new(clean_query) as Box<dyn rusqlite::types::ToSql>,
                        Box::new(top_k as i64),
                    ],
                )
            };

        let mut stmt = conn
            .prepare(&sql)
            .map_err(|e| format!("Prepare failed: {}", e))?;
        let param_refs: Vec<&dyn rusqlite::types::ToSql> =
            params_vec.iter().map(|p| p.as_ref()).collect();

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
                1.0f32 / (1.0f32 + rank.abs() as f32)
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
        )
        .ok();
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
    use rusqlite::Connection;

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

    /// 验证从旧版 v0 schema（含 `embedding BLOB NOT NULL`）迁移到 FTS5-only schema。
    /// 旧 DB 直接 DROP COLUMN 后应能正常 upsert，不再触发 NOT NULL 约束错误。
    #[test]
    fn test_migrate_legacy_embedding_column() {
        let dir = tempfile::tempdir().unwrap();
        let db_path = dir.path().join("legacy.db");

        // 1. 手工建一个旧 v0 schema 的 sections 表（含 embedding 列）
        {
            let conn = Connection::open(&db_path).unwrap();
            conn.execute(
                "CREATE TABLE sections (
                    id TEXT PRIMARY KEY,
                    doc_id TEXT NOT NULL,
                    text TEXT NOT NULL,
                    embedding BLOB NOT NULL,
                    metadata TEXT NOT NULL
                )",
                [],
            )
            .unwrap();
            conn.execute(
                "INSERT INTO sections (id, doc_id, text, embedding, metadata) VALUES (?1, ?2, ?3, ?4, ?5)",
                params!["legacy-1", "doc1", "legacy text", vec![0u8], "{}"],
            )
            .unwrap();
        }

        // 2. 触发 migration
        let store = SqliteVectorStore::new(&db_path).unwrap();

        // 3. 验证：`embedding` 列已 DROP，列数为 4
        let conn = Connection::open(&db_path).unwrap();
        let cols: Vec<String> = conn
            .prepare("PRAGMA table_info(sections)")
            .unwrap()
            .query_map([], |row| row.get::<_, String>(1))
            .unwrap()
            .filter_map(|r| r.ok())
            .collect();
        assert!(
            !cols.iter().any(|c| c == "embedding"),
            "embedding column should be dropped, got cols: {:?}",
            cols
        );
        assert_eq!(cols.len(), 4);

        // 4. 验证：旧数据保留 + 新 upsert 不再触发 NOT NULL 约束
        assert_eq!(store.count().unwrap(), 1);
        store
            .upsert(vec![VectorItem {
                id: "new-1".into(),
                doc_id: "doc2".into(),
                text: "post-migration text".into(),
                embedding: vec![],
                metadata: serde_json::json!({}),
            }])
            .unwrap();
        assert_eq!(store.count().unwrap(), 2);

        // 5. 验证：再次打开 DB（再次跑 migration）也是幂等的
        let _store2 = SqliteVectorStore::new(&db_path).unwrap();
    }
}
