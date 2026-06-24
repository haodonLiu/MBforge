//! Zvec 搜索封装 — 替代 SQLite 向量/FTS 存储。
//!
//! 使用 `zvec-bindings` 的同步 API 打开本地 collection，提供：
//! - 向量索引（HNSW + Cosine）
//! - 全文检索（FTS）
//! - 混合搜索（MultiQuery + RRF）

use std::path::Path;

use mbforge_infra::error::{AppError, AppResult, ErrorCode};
use zvec_bindings::{
    create_and_open_shared, CollectionSchema, Doc, FieldSchema, FtsQuery, MetricType, MultiQuery,
    RrfReranker, SharedCollection, VectorQuery,
};

/// 搜索结果。
#[derive(Debug, Clone)]
pub struct SearchResult {
    pub id: String,
    pub text: String,
    pub metadata: serde_json::Value,
    pub score: f32,
}

/// Zvec 搜索引擎。
pub struct SearchEngine {
    collection: SharedCollection,
    dim: usize,
}

impl SearchEngine {
    /// 打开或创建 Zvec collection。
    pub fn open(path: &Path, dim: usize) -> AppResult<Self> {
        if dim == 0 {
            return Err(AppError::new(
                ErrorCode::Unknown,
                "SearchEngine dimension must be > 0",
            ));
        }
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent)?;
        }

        let schema = CollectionSchema::builder("mbforge_kb")
            .map_err(|e| AppError::new(ErrorCode::Unknown, format!("schema builder: {e}")))?
            .field(FieldSchema::string("chunk_id").primary_key(true))
            .map_err(|e| AppError::new(ErrorCode::Unknown, format!("chunk_id field: {e}")))?
            .field(FieldSchema::string("doc_id").invert_index(true, false))
            .map_err(|e| AppError::new(ErrorCode::Unknown, format!("doc_id field: {e}")))?
            .field(FieldSchema::string("text").fts_tokenizer("standard"))
            .map_err(|e| AppError::new(ErrorCode::Unknown, format!("text field: {e}")))?
            .field(FieldSchema::string("metadata"))
            .map_err(|e| AppError::new(ErrorCode::Unknown, format!("metadata field: {e}")))?
            .field(
                FieldSchema::vector_fp32("embedding", dim)
                    .hnsw(16, 200)
                    .metric(MetricType::Cosine),
            )
            .map_err(|e| AppError::new(ErrorCode::Unknown, format!("embedding field: {e}")))?
            .build()
            .map_err(|e| AppError::new(ErrorCode::Unknown, format!("schema build: {e}")))?;

        let collection = create_and_open_shared(path, &schema, None)
            .map_err(|e| AppError::new(ErrorCode::Unknown, format!("open zvec: {e}")))?;

        Ok(Self { collection, dim })
    }

    /// 向量维度。
    pub fn dim(&self) -> usize {
        self.dim
    }

    /// 索引/重新索引一个文档的全部 chunks。
    pub fn index_document(
        &self,
        doc_id: &str,
        chunk_ids: &[String],
        texts: &[String],
        metadatas: &[String],
        embeddings: &[Vec<f32>],
    ) -> AppResult<()> {
        if chunk_ids.is_empty() {
            return Ok(());
        }

        for (i, v) in embeddings.iter().enumerate() {
            if v.len() != self.dim {
                return Err(AppError::new(
                    ErrorCode::Unknown,
                    format!(
                        "Vector dimension mismatch at index {i}: expected {}, got {}",
                        self.dim,
                        v.len()
                    ),
                ));
            }
        }

        self.delete_document(doc_id)?;

        let mut docs = Vec::with_capacity(chunk_ids.len());
        for i in 0..chunk_ids.len() {
            let mut doc = Doc::id(&chunk_ids[i]);
            doc.add_string("doc_id", doc_id)
                .map_err(|e| AppError::new(ErrorCode::Unknown, format!("doc field: {e}")))?;
            doc.add_string("text", &texts[i])
                .map_err(|e| AppError::new(ErrorCode::Unknown, format!("text field: {e}")))?;
            doc.add_string("metadata", &metadatas[i])
                .map_err(|e| AppError::new(ErrorCode::Unknown, format!("metadata field: {e}")))?;
            doc.add_vector_fp32("embedding", &embeddings[i])
                .map_err(|e| AppError::new(ErrorCode::Unknown, format!("embedding field: {e}")))?;
            docs.push(doc);
        }

        self.collection
            .insert(&docs)
            .map_err(|e| AppError::new(ErrorCode::Unknown, format!("zvec insert: {e}")))?;
        Ok(())
    }

    /// 删除一个文档的所有 chunks。
    pub fn delete_document(&self, doc_id: &str) -> AppResult<()> {
        self.collection
            .delete_by_filter(&format!("doc_id = '{}'", doc_id))
            .map_err(|e| AppError::new(ErrorCode::Unknown, format!("zvec delete: {e}")))?;
        Ok(())
    }

    /// 纯向量搜索。
    pub fn vector_search(
        &self,
        query_embedding: &[f32],
        top_k: usize,
        doc_id_filter: Option<&str>,
    ) -> AppResult<Vec<SearchResult>> {
        let mut q = VectorQuery::builder()
            .field("embedding")
            .vector_fp32(query_embedding)
            .topk(top_k)
            .build()
            .map_err(|e| AppError::new(ErrorCode::Unknown, format!("vector query: {e}")))?;

        if let Some(doc_id) = doc_id_filter {
            q = q.filter(&format!("doc_id = '{}'", doc_id));
        }

        let results = self
            .collection
            .query(&q)
            .map_err(|e| AppError::new(ErrorCode::Unknown, format!("zvec vector search: {e}")))?;

        Ok(results.iter().map(parse_row).collect())
    }

    /// 纯全文搜索。
    pub fn text_search(
        &self,
        query: &str,
        top_k: usize,
        doc_id_filter: Option<&str>,
    ) -> AppResult<Vec<SearchResult>> {
        let filter = doc_id_filter.map(|d| format!("doc_id = '{}'", d));
        let q = FtsQuery::new("text", query, top_k, filter.as_deref())
            .map_err(|e| AppError::new(ErrorCode::Unknown, format!("fts query: {e}")))?;

        let results = self
            .collection
            .query(&q)
            .map_err(|e| AppError::new(ErrorCode::Unknown, format!("zvec text search: {e}")))?;

        Ok(results.iter().map(parse_row).collect())
    }

    /// 混合搜索：向量 + FTS + RRF 融合。
    pub fn hybrid_search(
        &self,
        query_vec: &[f32],
        query_text: &str,
        top_k: usize,
        doc_id_filter: Option<&str>,
    ) -> AppResult<Vec<SearchResult>> {
        let filter = doc_id_filter.map(|d| format!("doc_id = '{}'", d));

        let vq = VectorQuery::builder()
            .field("embedding")
            .vector_fp32(query_vec)
            .topk(top_k * 3)
            .build()
            .map_err(|e| AppError::new(ErrorCode::Unknown, format!("vector query: {e}")))?;

        let fq = FtsQuery::new("text", query_text, top_k * 3, filter.as_deref())
            .map_err(|e| AppError::new(ErrorCode::Unknown, format!("fts query: {e}")))?;

        let multi = MultiQuery::new(vec![Box::new(vq), Box::new(fq)])
            .reranker(RrfReranker::with_top_n(top_k))
            .map_err(|e| AppError::new(ErrorCode::Unknown, format!("multi query: {e}")))?;

        let results = self
            .collection
            .query(&multi)
            .map_err(|e| AppError::new(ErrorCode::Unknown, format!("zvec hybrid search: {e}")))?;

        Ok(results.iter().map(parse_row).collect())
    }

    /// 总 chunk 数。
    pub fn count(&self) -> AppResult<usize> {
        self.collection
            .count()
            .map_err(|e| AppError::new(ErrorCode::Unknown, format!("zvec count: {e}")))
    }
}

fn parse_row(row: &zvec_bindings::SearchResult) -> SearchResult {
    SearchResult {
        id: row.pk().to_string(),
        text: row.field_as_string("text").unwrap_or_default(),
        metadata: serde_json::from_str(&row.field_as_string("metadata").unwrap_or_default())
            .unwrap_or_else(|_| serde_json::json!({})),
        score: row.score(),
    }
}
