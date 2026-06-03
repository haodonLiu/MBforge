//! 搜索结果类型定义
//!
//! SearchResult 被 lance_store 和 knowledge_base 共用。
//! 旧的 SqliteVectorStore 已移除，知识库搜索完全由 LanceDB 接管。

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchResult {
    pub id: String,
    pub text: String,
    pub metadata: serde_json::Value,
    pub score: f32,
}
