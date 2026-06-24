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
    // 以下字段扩展自 Python ExtractionResult (src/mbforge/parsers/molecule/extraction_result.py)
    #[serde(default)]
    pub esmiles: String,
    #[serde(default)]
    pub source: String,
    #[serde(default)]
    pub moldet_conf: f64,
    #[serde(default)]
    pub scribe_conf: f64,
    #[serde(default)]
    pub composite_conf: f64,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub bbox_pdf: Option<[f64; 4]>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub page_idx: Option<usize>,
    #[serde(default)]
    pub mol_img_path: Option<String>,
    #[serde(default)]
    pub status: String,
}

impl ExtractionResult {
    pub fn new(context_text: &str) -> Self {
        Self {
            name: String::new(),
            context_text: context_text.to_string(),
            properties: serde_json::json!({}),
            esmiles: String::new(),
            source: "image".into(),
            moldet_conf: 0.0,
            scribe_conf: 0.0,
            composite_conf: 0.0,
            bbox_pdf: None,
            page_idx: None,
            mol_img_path: None,
            status: "pending".into(),
        }
    }

    pub fn with_esmiles(context_text: &str, esmiles: &str) -> Self {
        let mut s = Self::new(context_text);
        s.esmiles = esmiles.to_string();
        s
    }
}

// ---------------------------------------------------------------------------
// Classification / extraction types (from commands/classifier.rs + extractor.rs)
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct PageClassification {
    pub page_idx: usize,
    pub text_density: f64,
    pub is_scanned: bool,
    pub has_molecular_patterns: bool,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct DocumentClassification {
    pub text_density: f64,
    pub is_scanned: bool,
    pub has_molecular_patterns: bool,
    pub metadata_hints: Option<serde_json::Value>,
    pub pages: Vec<PageClassification>,
    pub needs_confirmation: bool,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ActivityData {
    pub activity_type: String,
    pub value: f64,
    pub units: String,
    pub context: String,
}
