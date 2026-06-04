//! SQLite 向量存储 — 替代 LanceDB
//!
//! 使用 SQLite BLOB 存储向量，Rust 侧暴力余弦搜索。
//! 对于 MBForge 的规模（<20K chunks），暴力搜索 <10ms，不需要 ANN 索引。
//! 零额外依赖，与 molecules.db / file_cache 共享 SQLite 生态。

use std::path::Path;
use std::sync::Mutex;

use rusqlite::{params, Connection, ToSql};

use super::vector_store::SearchResult;

/// SQLite 向量存储
pub struct SqliteVectorStore {
    conn: Mutex<Connection>,
    dim: usize,
}

impl SqliteVectorStore {
    /// 打开或创建向量数据库
    pub fn open(db_path: &Path, dim: usize) -> Result<Self, String> {
        if let Some(parent) = db_path.parent() {
            std::fs::create_dir_all(parent)
                .map_err(|e| format!("Create dir failed: {}", e))?;
        }

        let conn = Connection::open(db_path)
            .map_err(|e| format!("Open DB failed: {}", e))?;

        conn.execute_batch(
            "PRAGMA journal_mode=WAL;
             PRAGMA busy_timeout=5000;",
        )
        .map_err(|e| format!("Set pragma failed: {}", e))?;

        // 向量表
        conn.execute(
            "CREATE TABLE IF NOT EXISTS vectors (
                chunk_id TEXT PRIMARY KEY,
                doc_id TEXT NOT NULL,
                text TEXT NOT NULL,
                metadata TEXT NOT NULL,
                embedding BLOB NOT NULL
            )",
            [],
        )
        .map_err(|e| format!("Create vectors table failed: {}", e))?;

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_vectors_doc_id ON vectors(doc_id)",
            [],
        )
        .map_err(|e| format!("Create index failed: {}", e))?;

        Ok(Self {
            conn: Mutex::new(conn),
            dim,
        })
    }

    /// 写入向量（upsert 语义）
    pub fn upsert_vectors(
        &self,
        chunk_ids: &[String],
        doc_id: &str,
        texts: &[String],
        metadatas: &[String],
        vectors: &[Vec<f32>],
    ) -> Result<(), String> {
        if chunk_ids.is_empty() {
            return Ok(());
        }

        let conn = self.conn.lock().map_err(|e| format!("Lock error: {}", e))?;
        let tx = conn
            .unchecked_transaction()
            .map_err(|e| format!("Transaction failed: {}", e))?;

        // 先删除该 doc_id 的旧数据
        tx.execute("DELETE FROM vectors WHERE doc_id = ?1", params![doc_id])
            .map_err(|e| format!("Delete old vectors failed: {}", e))?;

        // 插入新数据
        for i in 0..chunk_ids.len() {
            let fp_bytes = f32_vec_to_bytes(&vectors[i]);
            tx.execute(
                "INSERT OR REPLACE INTO vectors (chunk_id, doc_id, text, metadata, embedding)
                 VALUES (?1, ?2, ?3, ?4, ?5)",
                params![chunk_ids[i], doc_id, texts[i], metadatas[i], fp_bytes],
            )
            .map_err(|e| format!("Insert vector failed: {}", e))?;
        }

        tx.commit().map_err(|e| format!("Commit failed: {}", e))?;
        Ok(())
    }

    /// 向量搜索 — 暴力余弦相似度
    pub fn search_vector(
        &self,
        query_embedding: &[f32],
        top_k: usize,
        filter_doc_id: Option<&str>,
    ) -> Result<Vec<SearchResult>, String> {
        let conn = self.conn.lock().map_err(|e| format!("Lock error: {}", e))?;

        let (sql, query_params): (&str, Vec<Box<dyn ToSql>>) = if let Some(doc_id) = filter_doc_id {
            (
                "SELECT chunk_id, text, metadata, embedding FROM vectors WHERE doc_id = ?1",
                vec![Box::new(doc_id.to_string())],
            )
        } else {
            (
                "SELECT chunk_id, text, metadata, embedding FROM vectors",
                vec![],
            )
        };

        let mut stmt = conn
            .prepare(sql)
            .map_err(|e| format!("Prepare failed: {}", e))?;

        let param_refs: Vec<&dyn ToSql> = query_params.iter().map(|p| p.as_ref()).collect();
        let rows = stmt
            .query_map(param_refs.as_slice(), |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, String>(1)?,
                    row.get::<_, String>(2)?,
                    row.get::<_, Vec<u8>>(3)?,
                ))
            })
            .map_err(|e| format!("Query failed: {}", e))?;

        // 计算余弦相似度并排序
        let mut scored: Vec<(String, String, serde_json::Value, f32)> = Vec::new();
        for row in rows {
            let (chunk_id, text, meta_str, embedding_bytes) =
                row.map_err(|e| format!("Row error: {}", e))?;

            let embedding = bytes_to_f32_vec(&embedding_bytes);
            let similarity = cosine_similarity_f32(query_embedding, &embedding);

            let metadata: serde_json::Value =
                serde_json::from_str(&meta_str).unwrap_or(serde_json::json!({}));

            scored.push((chunk_id, text, metadata, similarity));
        }

        // 按相似度降序排序
        scored.sort_by(|a, b| b.3.partial_cmp(&a.3).unwrap_or(std::cmp::Ordering::Equal));
        scored.truncate(top_k);

        Ok(scored
            .into_iter()
            .map(|(id, text, metadata, score)| SearchResult {
                id,
                text,
                metadata,
                score,
            })
            .collect())
    }

    /// 删除指定文档的所有向量
    pub fn delete_doc(&self, doc_id: &str) -> Result<(), String> {
        let conn = self.conn.lock().map_err(|e| format!("Lock error: {}", e))?;
        conn.execute("DELETE FROM vectors WHERE doc_id = ?1", params![doc_id])
            .map_err(|e| format!("Delete failed: {}", e))?;
        Ok(())
    }

    /// 向量数量
    pub fn count(&self) -> Result<usize, String> {
        let conn = self.conn.lock().map_err(|e| format!("Lock error: {}", e))?;
        let count: i64 = conn
            .query_row("SELECT COUNT(*) FROM vectors", [], |r| r.get(0))
            .map_err(|e| format!("Count failed: {}", e))?;
        Ok(count as usize)
    }
}

// ============================================================================
// 向量工具函数
// ============================================================================

/// f32 向量 → 字节（小端序）
fn f32_vec_to_bytes(v: &[f32]) -> Vec<u8> {
    let mut bytes = Vec::with_capacity(v.len() * 4);
    for &f in v {
        bytes.extend_from_slice(&f.to_le_bytes());
    }
    bytes
}

/// 字节 → f32 向量
fn bytes_to_f32_vec(bytes: &[u8]) -> Vec<f32> {
    bytes
        .chunks_exact(4)
        .map(|chunk| f32::from_le_bytes([chunk[0], chunk[1], chunk[2], chunk[3]]))
        .collect()
}

/// 余弦相似度
fn cosine_similarity_f32(a: &[f32], b: &[f32]) -> f32 {
    if a.len() != b.len() || a.is_empty() {
        return 0.0;
    }
    let (mut dot, mut norm_a, mut norm_b) = (0.0f32, 0.0f32, 0.0f32);
    for (x, y) in a.iter().zip(b.iter()) {
        dot += x * y;
        norm_a += x * x;
        norm_b += y * y;
    }
    let denom = norm_a.sqrt() * norm_b.sqrt();
    if denom == 0.0 { 0.0 } else { dot / denom }
}

/// Reciprocal Rank Fusion — 融合 FTS5 和向量搜索结果
pub fn reciprocal_rank_fusion(
    fts_results: Vec<SearchResult>,
    vec_results: Vec<SearchResult>,
    top_k: usize,
) -> Vec<SearchResult> {
    const K: f32 = 60.0;
    let mut scores: std::collections::HashMap<String, (f32, String, serde_json::Value)> =
        std::collections::HashMap::new();

    for (rank, r) in fts_results.into_iter().enumerate() {
        let entry = scores
            .entry(r.id.clone())
            .or_insert((0.0, r.text.clone(), r.metadata.clone()));
        entry.0 += 1.0 / (K + rank as f32);
    }

    for (rank, r) in vec_results.into_iter().enumerate() {
        let entry = scores
            .entry(r.id.clone())
            .or_insert((0.0, r.text.clone(), r.metadata.clone()));
        entry.0 += 1.0 / (K + rank as f32);
    }

    let mut results: Vec<SearchResult> = scores
        .into_iter()
        .map(|(id, (score, text, metadata))| SearchResult {
            id,
            text,
            metadata,
            score,
        })
        .collect();

    results.sort_by(|a, b| b.score.partial_cmp(&a.score).unwrap_or(std::cmp::Ordering::Equal));
    results.truncate(top_k);
    results
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_vector_roundtrip() {
        let dir = tempfile::tempdir().unwrap();
        let db_path = dir.path().join("test.db");
        let store = SqliteVectorStore::open(&db_path, 4).unwrap();

        let ids = vec!["c1".to_string(), "c2".to_string()];
        let texts = vec!["hello".to_string(), "world".to_string()];
        let metas = vec!["{}".to_string(), "{}".to_string()];
        let vecs = vec![
            vec![1.0, 0.0, 0.0, 0.0],
            vec![0.0, 1.0, 0.0, 0.0],
        ];

        store.upsert_vectors(&ids, "doc1", &texts, &metas, &vecs).unwrap();
        assert_eq!(store.count().unwrap(), 2);

        // 搜索与 [1,0,0,0] 最相似的
        let results = store.search_vector(&[1.0, 0.0, 0.0, 0.0], 2, None).unwrap();
        assert_eq!(results.len(), 2);
        assert_eq!(results[0].id, "c1"); // 最相似
        assert!(results[0].score > results[1].score);
    }

    #[test]
    fn test_delete_doc() {
        let dir = tempfile::tempdir().unwrap();
        let db_path = dir.path().join("test.db");
        let store = SqliteVectorStore::open(&db_path, 4).unwrap();

        store.upsert_vectors(
            &["c1".into()],
            "doc1",
            &["text".into()],
            &["{}".into()],
            &[vec![1.0, 0.0, 0.0, 0.0]],
        ).unwrap();

        store.delete_doc("doc1").unwrap();
        assert_eq!(store.count().unwrap(), 0);
    }

    #[test]
    fn test_cosine_similarity() {
        let a = vec![1.0, 0.0, 0.0];
        let b = vec![1.0, 0.0, 0.0];
        assert!((cosine_similarity_f32(&a, &b) - 1.0).abs() < 0.01);

        let c = vec![0.0, 1.0, 0.0];
        assert!(cosine_similarity_f32(&a, &c).abs() < 0.01);
    }

    #[test]
    fn test_rrf_fusion() {
        let fts = vec![
            SearchResult { id: "a".into(), text: "A".into(), metadata: serde_json::json!({}), score: 0.9 },
            SearchResult { id: "b".into(), text: "B".into(), metadata: serde_json::json!({}), score: 0.7 },
        ];
        let vec = vec![
            SearchResult { id: "b".into(), text: "B".into(), metadata: serde_json::json!({}), score: 0.95 },
            SearchResult { id: "c".into(), text: "C".into(), metadata: serde_json::json!({}), score: 0.8 },
        ];

        let fused = reciprocal_rank_fusion(fts, vec, 10);
        assert_eq!(fused.len(), 3);
        assert_eq!(fused[0].id, "b"); // 两个列表都有 b，RRF 分数最高
    }
}
