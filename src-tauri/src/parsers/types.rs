use serde::{Deserialize, Serialize};
use std::path::PathBuf;

/// === A/B 共享的数据结构 ===

/// 文档处理上下文 — 整个 process 期间传递的状态
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DocProcessingContext {
    pub source_path: PathBuf,
    pub parser_used: String,
    pub raw_text: String,
    pub images: Vec<ImageRef>,
    pub page_count: usize,
    pub doc_type: Option<String>,
    pub user_request: String,
}

impl DocProcessingContext {
    pub fn new(path: &str, user_request: &str) -> Self {
        Self {
            source_path: PathBuf::from(path),
            parser_used: String::new(),
            raw_text: String::new(),
            images: Vec::new(),
            page_count: 0,
            doc_type: None,
            user_request: user_request.to_string(),
        }
    }
}

/// 图片引用 — MinerU 输出的配图
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ImageRef {
    pub filename: String,
    pub page: usize,
    pub region: Option<String>,
    pub description: Option<String>,
    pub smiles: Option<String>,
}

/// 文档结构分析结果（Stage 1 输出）
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DocStructure {
    pub doc_type: String,
    pub page_count: usize,
    pub has_compound_tables: bool,
    pub has_chemical_structures: bool,
    pub has_activity_data: bool,
    pub estimated_sections: Vec<String>,
    pub key_terms: Vec<String>,
    pub recommended_approach: String,
}

/// 提取计划（Stage 1.5 输出）
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExtractionPlan {
    pub target_sections: Vec<String>,
    pub extraction_types: Vec<String>,
    pub skip_sections: Vec<String>,
}

/// 最终文档报告
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DocumentReport {
    pub metadata: super::post_process::DocumentMetadata,
    pub compounds: Vec<super::post_process::CompoundEntry>,
    pub activities: Vec<super::post_process::ActivityEntry>,
    pub key_findings: Vec<super::post_process::FindingEntry>,
    pub sar_analysis: String,
    pub uncertain_items: Vec<super::post_process::UncertainItem>,
    pub report_markdown: String,
}

/// 处理阶段日志
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StageLog {
    pub stage: usize,
    pub name: String,
    pub status: String,
    pub items_processed: usize,
    pub tokens_used: u32,
    pub errors: Vec<String>,
}

/// 处理日志
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProcessingLog {
    pub stages: Vec<StageLog>,
    pub uncertain_items: Vec<super::post_process::UncertainItem>,
    pub warnings: Vec<String>,
}
