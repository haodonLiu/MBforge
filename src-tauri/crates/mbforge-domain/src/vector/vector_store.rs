//! 搜索结果类型定义
//!
//! SearchResult 被 sqlite_vector_store 和 knowledge_base 共用。

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchResult {
    pub id: String,
    pub text: String,
    pub metadata: serde_json::Value,
    pub score: f32,
}
