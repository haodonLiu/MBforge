//! 共享类型 — 跨层使用的数据结构
//!
//! 设计原则：
//! - 不依赖任何其他模块（core/parsers/commands 均不依赖）
//! - 只包含纯数据类型（struct/enum），不包含业务逻辑
//! - core 和 parsers 均可导入，避免反向依赖

use serde::{Deserialize, Serialize};

// ---------------------------------------------------------------------------
// Document structure types (from parsers/headings.rs + parsers/sections.rs)
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Heading {
    pub level: usize,
    pub title: String,
    pub line_num: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SectionChunk {
    pub title: String,
    pub path: String,
    pub text: String,
    pub page_start: Option<usize>,
    pub page_end: Option<usize>,
    pub line_start: usize,
    pub line_end: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TreeNode {
    pub title: String,
    pub node_id: String,
    pub line_num: usize,
    pub nodes: Vec<TreeNode>,
}

// ---------------------------------------------------------------------------
// Extraction types (from parsers/association.rs)
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExtractionResult {
    pub name: String,
    pub context_text: String,
    pub properties: serde_json::Value,
}

impl ExtractionResult {
    pub fn new(context_text: &str) -> Self {
        Self {
            name: String::new(),
            context_text: context_text.to_string(),
            properties: serde_json::json!({}),
        }
    }
}
