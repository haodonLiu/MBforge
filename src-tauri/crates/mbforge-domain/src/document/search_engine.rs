//! Zvec 搜索封装 — 通过 Python sidecar HTTP 服务实现。
//!
//! Rust 端不再直接链接本地 `zvec-bindings`，而是调用 sidecar 暴露的
//! `/api/v1/zvec/*` 端点完成 collection 打开、索引、删除和搜索。
//! 使用同步 HTTP 客户端 `ureq`（不依赖 tokio runtime），因此可以在异步
//! Tauri 命令/单测上下文中安全创建和销毁。

use std::path::{Path, PathBuf};
use std::time::Duration;

use mbforge_infra::config::constants::sidecar_url;
use mbforge_infra::error::{AppError, AppResult, ErrorCode};
use serde::{Deserialize, Serialize};

/// 搜索结果。
#[derive(Debug, Clone)]
pub struct SearchResult {
    pub id: String,
    pub text: String,
    pub metadata: serde_json::Value,
    pub score: f32,
}

/// Zvec 搜索引擎（HTTP 客户端封装）。
pub struct SearchEngine {
    collection_path: PathBuf,
    dim: usize,
    base_url: String,
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

        let base_url = sidecar_url();
        let engine = Self {
            collection_path: path.to_path_buf(),
            dim,
            base_url,
        };
        engine.open_collection()?;
        Ok(engine)
    }

    /// 向量维度。
    pub fn dim(&self) -> usize {
        self.dim
    }

    fn sidecar_url(&self, endpoint: &str) -> String {
        format!(
            "{}/api/v1/zvec/{}",
            self.base_url.trim_end_matches('/'),
            endpoint
        )
    }

    fn open_collection(&self) -> AppResult<()> {
        let path_str = self.collection_path.to_string_lossy().to_string();
        let body = OpenRequest {
            path: path_str,
            dim: self.dim,
        };
        self.post::<OpenRequest, GenericResponse>("collection/open", &body)
            .map(|_| ())
    }

    fn post<B, R>(&self, endpoint: &str, body: &B) -> AppResult<R>
    where
        B: Serialize,
        R: for<'de> Deserialize<'de>,
    {
        let url = self.sidecar_url(endpoint);
        let resp = ureq::post(&url)
            .set("Content-Type", "application/json")
            .timeout(Duration::from_secs(120))
            .send_json(body)
            .map_err(|e| AppError {
                code: ErrorCode::Network,
                message: format!("sidecar zvec request failed: {e}"),
                path: Some(url.clone()),
                suggestion: Some("检查 Python sidecar 是否在运行".to_string()),
            })?;

        let status = resp.status();
        let text = resp.into_string().unwrap_or_default();

        if status >= 400 {
            let err: GenericResponse = serde_json::from_str(&text).unwrap_or(GenericResponse {
                error: Some(text.clone()),
            });
            return Err(AppError {
                code: ErrorCode::ApiError,
                message: err.error.unwrap_or_else(|| text.clone()),
                path: Some(url),
                suggestion: None,
            });
        }

        serde_json::from_str(&text).map_err(|e| AppError {
            code: ErrorCode::ApiError,
            message: format!("failed to parse sidecar response: {e}, body: {text}"),
            path: Some(url),
            suggestion: None,
        })
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

        let body = IndexRequest {
            doc_id: doc_id.to_string(),
            chunk_ids: chunk_ids.to_vec(),
            texts: texts.to_vec(),
            metadatas: metadatas.to_vec(),
            embeddings: embeddings.to_vec(),
        };
        self.post::<IndexRequest, IndexResponse>("index", &body)?;
        Ok(())
    }

    /// 删除一个文档的所有 chunks。
    pub fn delete_document(&self, doc_id: &str) -> AppResult<()> {
        let body = DeleteRequest {
            doc_id: doc_id.to_string(),
        };
        self.post::<DeleteRequest, GenericResponse>("delete", &body)?;
        Ok(())
    }

    /// 纯向量搜索。
    pub fn vector_search(
        &self,
        query_embedding: &[f32],
        top_k: usize,
        doc_id_filter: Option<&str>,
    ) -> AppResult<Vec<SearchResult>> {
        let body = VectorSearchRequest {
            query_embedding: query_embedding.to_vec(),
            top_k,
            doc_id_filter: doc_id_filter.map(String::from),
        };
        let resp: SearchResponse = self.post("search/vector", &body)?;
        Ok(resp.results.into_iter().map(Into::into).collect())
    }

    /// 纯全文搜索。
    pub fn text_search(
        &self,
        query: &str,
        top_k: usize,
        doc_id_filter: Option<&str>,
    ) -> AppResult<Vec<SearchResult>> {
        let body = TextSearchRequest {
            query: query.to_string(),
            top_k,
            doc_id_filter: doc_id_filter.map(String::from),
        };
        let resp: SearchResponse = self.post("search/text", &body)?;
        Ok(resp.results.into_iter().map(Into::into).collect())
    }

    /// 混合搜索：向量 + FTS + RRF 融合。
    pub fn hybrid_search(
        &self,
        query_vec: &[f32],
        query_text: &str,
        top_k: usize,
        doc_id_filter: Option<&str>,
    ) -> AppResult<Vec<SearchResult>> {
        let body = HybridSearchRequest {
            query_vec: query_vec.to_vec(),
            query_text: query_text.to_string(),
            top_k,
            doc_id_filter: doc_id_filter.map(String::from),
        };
        let resp: SearchResponse = self.post("search/hybrid", &body)?;
        Ok(resp.results.into_iter().map(Into::into).collect())
    }

    /// 总 chunk 数。
    pub fn count(&self) -> AppResult<usize> {
        let body = serde_json::json!({});
        let resp: CountResponse = self.post("count", &body)?;
        Ok(resp.count)
    }
}

// ============================================================================
// DTOs
// ============================================================================

#[derive(Debug, Clone, Serialize)]
struct OpenRequest {
    path: String,
    dim: usize,
}

#[derive(Debug, Clone, Serialize)]
struct IndexRequest {
    doc_id: String,
    chunk_ids: Vec<String>,
    texts: Vec<String>,
    metadatas: Vec<String>,
    embeddings: Vec<Vec<f32>>,
}

#[derive(Debug, Clone, Deserialize)]
struct IndexResponse {
    #[allow(dead_code)]
    indexed: usize,
}

#[derive(Debug, Clone, Serialize)]
struct DeleteRequest {
    doc_id: String,
}

#[derive(Debug, Clone, Serialize)]
struct VectorSearchRequest {
    query_embedding: Vec<f32>,
    top_k: usize,
    #[serde(skip_serializing_if = "Option::is_none")]
    doc_id_filter: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
struct TextSearchRequest {
    query: String,
    top_k: usize,
    #[serde(skip_serializing_if = "Option::is_none")]
    doc_id_filter: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
struct HybridSearchRequest {
    query_vec: Vec<f32>,
    query_text: String,
    top_k: usize,
    #[serde(skip_serializing_if = "Option::is_none")]
    doc_id_filter: Option<String>,
}

#[derive(Debug, Clone, Deserialize)]
struct SearchResponse {
    #[serde(default)]
    results: Vec<SearchResultDto>,
}

#[derive(Debug, Clone, Deserialize)]
struct SearchResultDto {
    id: String,
    text: String,
    #[serde(default)]
    metadata: serde_json::Value,
    #[serde(default)]
    score: f32,
}

impl From<SearchResultDto> for SearchResult {
    fn from(dto: SearchResultDto) -> Self {
        Self {
            id: dto.id,
            text: dto.text,
            metadata: dto.metadata,
            score: dto.score,
        }
    }
}

#[derive(Debug, Clone, Deserialize)]
struct CountResponse {
    count: usize,
}

#[derive(Debug, Clone, Deserialize)]
struct GenericResponse {
    #[serde(default)]
    error: Option<String>,
}
