use serde::{Deserialize, Serialize};
use std::path::PathBuf;

use crate::commands::classifier::DocumentClassification;
use crate::commands::extractor::ActivityData;
use crate::core::types::{Heading, SectionChunk};
use crate::parsers::chem::vlm_chem::ChemImageResult;
use crate::parsers::chem::vlm_chem::DetectedMolecule;

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

/// OCR 布局块 — MinerU layout.json 解析出的单个文本/图像/表格区域
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OcrBlock {
    /// 页码（1-based）
    pub page: usize,
    /// 块类型: text, image, table, formula, chart, header, footer, seal 等
    pub block_type: String,
    /// 边界框 [x1, y1, x2, y2]（PDF 原始坐标，左下角原点）
    pub bbox: [f64; 4],
    /// 文本内容（仅 text 类型有意义）
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub content: Option<String>,
    /// 块在页面中的序号
    pub index: usize,
    /// 旋转角度（0/90/180/270）
    #[serde(default)]
    pub angle: i32,
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
    /// Stage 2b 分子图像检测结果（filename → ChemImageResult）。
    ///
    /// 之前在 pipeline.rs 是 local 变量，没挂到 ctx 上 → DocumentReport
    /// / 前端看不到"VLM 识别了哪些分子图"。[方案 2] 修复。
    #[serde(default)]
    pub chem_images: std::collections::HashMap<String, ChemImageResult>,
    /// Stage 2b 检测到的分子原始记录（DetectedMolecule 列表）。
    /// 包含 page / crop_path / moldet_confidence 等元数据。
    #[serde(default)]
    pub detected_molecules: Vec<DetectedMolecule>,
    /// LitAgent 是否在 Stage 4 后做过二次审阅
    /// ([方案 3] 后续 PR 接 LiteratureAgent 时写入)
    #[serde(default)]
    pub lit_reviewed: bool,
    /// Stage 0.7 文档结构树（heading 层级嵌套），由 `sections::build_tree` 生成。
    /// 存到 ctx 上是为了让 `DocumentTreeIndex::index_document` 能直接消费，
    /// 避免重复构建。`Some` 表示已生成（无论是否非空）。
    #[serde(default)]
    pub document_tree: Option<Vec<crate::core::types::TreeNode>>,
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
            chem_images: std::collections::HashMap::new(),
            detected_molecules: Vec::new(),
            lit_reviewed: false,
            document_tree: None,
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
    /// LitAgent 是否在 Stage 4 后做过二次审阅（[方案 3]）
    #[serde(default)]
    pub lit_reviewed: bool,
    /// LitAgent 决策摘要（仅当 lit_reviewed=true 时有意义）
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub lit_decision_summary: Option<String>,
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

#[cfg(test)]
mod tests {
    use super::*;

    /// [方案 2] 验证 chem_images / detected_molecules / lit_reviewed 字段
    /// 在 new() 时正确初始化为空状态，调用方可以无 panic 地填充。
    #[test]
    fn test_doc_processing_context_new_initializes_new_fields() {
        let ctx = DocProcessingContext::new("/tmp/p.pdf", "extract mols");
        assert!(ctx.chem_images.is_empty());
        assert!(ctx.detected_molecules.is_empty());
        assert!(!ctx.lit_reviewed);
    }

    /// [方案 2] chem_images 用 filename 作 key，可以多次插入不同图。
    #[test]
    fn test_doc_processing_context_chem_images_insert() {
        let mut ctx = DocProcessingContext::new("/tmp/p.pdf", "");
        ctx.chem_images.insert(
            "page_0003_mol_000.png".to_string(),
            ChemImageResult {
                esmiles: "CCO".to_string(),
                confidence: 0.91,
            },
        );
        assert_eq!(ctx.chem_images.len(), 1);
        assert_eq!(
            ctx.chem_images
                .get("page_0003_mol_000.png")
                .unwrap()
                .esmiles,
            "CCO"
        );
    }

    /// [方案 2] detected_molecules 是 Vec，可以 append 多次 Stage 2b 的结果。
    #[test]
    fn test_doc_processing_context_detected_molecules_append() {
        let mut ctx = DocProcessingContext::new("/tmp/p.pdf", "");
        ctx.detected_molecules.push(DetectedMolecule {
            esmiles: "CCO".into(),
            confidence: 0.87,
            moldet_conf: 0.92,
            page: 3,
            crop_path: "/tmp/page_0003_mol_000.png".into(),
            bbox_pdf: [100.0, 400.0, 200.0, 500.0],
        });
        assert_eq!(ctx.detected_molecules.len(), 1);
        assert_eq!(ctx.detected_molecules[0].page, 3);
        assert_eq!(ctx.detected_molecules[0].esmiles, "CCO");
    }

    /// [方案 3] DocumentReport.lit_reviewed 默认 false，lit_decision_summary 默认 None。
    /// 这保证旧的 JSON 序列化数据反序列化不报错（向后兼容）。
    #[test]
    fn test_document_report_lit_fields_default() {
        // 序列化为 JSON 再反序列化 — 模拟 cache hit / 旧数据
        let report = DocumentReport {
            metadata: DocumentMetadata {
                title: None,
                authors: vec![],
                document_type: String::new(),
                key_targets: vec![],
                source_file: None,
            },
            compounds: vec![],
            activities: vec![],
            key_findings: vec![],
            sar_analysis: String::new(),
            uncertain_items: vec![],
            report_markdown: String::new(),
            lit_reviewed: false,
            lit_decision_summary: None,
        };
        let json = serde_json::to_string(&report).unwrap();
        let parsed: DocumentReport = serde_json::from_str(&json).unwrap();
        assert!(!parsed.lit_reviewed);
        assert!(parsed.lit_decision_summary.is_none());
    }
}
