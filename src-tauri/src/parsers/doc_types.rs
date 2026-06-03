use serde::{Deserialize, Serialize};
use std::path::PathBuf;

use crate::commands::classifier::DocumentClassification;
use crate::commands::extractor::ActivityData;
use crate::core::types::{Heading, SectionChunk};

// ---------------------------------------------------------------------------
// Core pipeline types
// ---------------------------------------------------------------------------

/// 图片引用 — MinerU 输出的配图
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ImageRef {
    pub filename: String,
    pub page: usize,
    pub region: Option<String>,
    pub description: Option<String>,
    pub esmiles: Option<String>,
    /// 图片在项目目录中的相对路径（如 "media/doc-slug/img-1.png"）
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub rel_path: Option<String>,
}

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
    pub headings: Vec<Heading>,
    pub sections: Vec<SectionChunk>,
    pub page_texts: Vec<String>,
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
            headings: Vec::new(),
            sections: Vec::new(),
            page_texts: Vec::new(),
        }
    }
}

/// Unified PDF parsing result.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PdfParseResult {
    /// Extracted text/markdown content.
    pub content: String,
    /// Classification result.
    pub classification: DocumentClassification,
    /// Chunks after splitting.
    pub chunks: Vec<String>,
    /// Extracted esmiles candidates.
    pub esmiles: Vec<String>,
    /// Extracted activity data.
    pub activities: Vec<ActivityData>,
    /// Parser used: "pdf_inspector", "llama_parse", "uniparser", or "mineru".
    pub parser: String,
    /// Page count.
    pub page_count: usize,
    /// Images extracted (MinerU path only).
    pub images: Vec<ImageRef>,
    /// Document headings extracted.
    pub headings: Vec<Heading>,
    /// Section chunks (section-based content splitting).
    pub sections: Vec<SectionChunk>,
    /// Per-page raw text (populated if page mapping available).
    pub page_texts: Vec<String>,
}

// ---------------------------------------------------------------------------
// Post-processing types
// ---------------------------------------------------------------------------

/// LLM 后处理结果 — 结构化报告 + 机器可读数据
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PostProcessResult {
    /// 完整的 Markdown 格式报告（人类可读）
    pub report: String,
    /// 结构化数据（机器可读）
    pub data: StructuredData,
    /// 使用的模型
    pub model: String,
    /// token 使用量
    pub tokens_used: Option<u32>,
    /// 分批处理的批次数
    pub batch_count: usize,
}

/// 结构化数据 — 与报告一一对应
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StructuredData {
    pub metadata: DocumentMetadata,
    pub summary: String,
    pub compounds: Vec<CompoundEntry>,
    pub activities: Vec<ActivityEntry>,
    pub key_findings: Vec<FindingEntry>,
    pub uncertain_items: Vec<UncertainItem>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DocumentMetadata {
    pub title: Option<String>,
    pub authors: Vec<String>,
    pub document_type: String,
    pub key_targets: Vec<String>,
    pub source_file: Option<String>,
}

/// 理化性质条目 — 活性或理化数据
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PhysicochemicalProperty {
    pub property_type: String,
    pub value: f64,
    pub unit: String,
    pub source_quote: String,
    pub confidence: String,
}

/// 化合物条目 — 带溯源和置信度
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CompoundEntry {
    /// 化合物名称
    pub name: String,
    /// SMILES 字符串（如果能确认）
    #[serde(rename = "smiles")]
    pub esmiles: Option<String>,
    /// 所属类别（如 JAK inhibitor, MRGPRX2 antagonist）
    pub category: Option<String>,
    /// 关键描述
    pub description: String,
    /// 在原文中的位置引用（页码或段落）
    pub source_ref: String,
    /// 置信度: high / medium / low
    pub confidence: String,
    /// 不确定的原因（仅当 confidence != high 时）
    pub uncertainty_reason: Option<String>,
    /// 理化性质数据列表（专利分子提取增强）
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub physicochemical_props: Option<Vec<PhysicochemicalProperty>>,
    /// 关联的图像文件名列表
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub related_images: Option<Vec<String>>,
    /// VLM 图像识别验证后的 E-SMILES
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub vlm_verified_esmiles: Option<String>,
    /// 化合物在原文中的页码位置
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub page_location: Option<usize>,
}

/// 活性数据条目 — 带溯源
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ActivityEntry {
    /// 化合物（名称或 SMILES）
    pub compound: String,
    /// 活性类型
    pub activity_type: String,
    /// 数值
    pub value: f64,
    /// 单位
    pub units: String,
    /// 靶点
    pub target: Option<String>,
    /// 原文上下文（精确引用）
    pub source_quote: String,
    /// 来源页码/段落
    pub source_ref: String,
    pub confidence: String,
    pub uncertainty_reason: Option<String>,
}

/// 关键发现条目 — 带溯源
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FindingEntry {
    /// 发现内容
    pub finding: String,
    /// 支撑证据（原文引用）
    pub evidence: String,
    /// 来源
    pub source_ref: String,
    pub confidence: String,
    pub uncertainty_reason: Option<String>,
}

/// 不确定项 — 需要人工审核的条目
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UncertainItem {
    /// 项目类型: compound / activity / finding / classification
    pub item_type: String,
    /// 内容描述
    pub content: String,
    /// 不确定的原因
    pub reason: String,
    /// 建议的审核动作
    pub suggested_action: String,
}

// ---------------------------------------------------------------------------
// Stage / report types
// ---------------------------------------------------------------------------

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
    pub metadata: DocumentMetadata,
    pub compounds: Vec<CompoundEntry>,
    pub activities: Vec<ActivityEntry>,
    pub key_findings: Vec<FindingEntry>,
    pub sar_analysis: String,
    pub uncertain_items: Vec<UncertainItem>,
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
    pub uncertain_items: Vec<UncertainItem>,
    pub warnings: Vec<String>,
}
