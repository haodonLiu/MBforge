//! PDF 解析 Facade — 阻止 commands/ 直接穿透调用 parsers/。
//!
//! 所有 Tauri 命令层对 PDF 解析的调用都应通过此 facade，
//! 由核心层内部调度 parsers/ 子系统。

use std::path::{Path, PathBuf};

// Re-export types that commands/ needs
pub use crate::parsers::doc_types::{OcrBlock, PdfParseResult, PostProcessResult};
pub use crate::parsers::pipeline::{ClassifyResult, WorkflowResult, PipelineOutput, IndexResult};
// Note: ClassifyResult re-exported from pipeline::extract via pipeline.rs
pub use crate::parsers::chem::association::ActivityEntry;
pub use crate::parsers::chem::chem_validate::separate_esmiles_layers;
pub use crate::parsers::chem::vlm_chem::DetectedMolecule;

// ---------------------------------------------------------------------------
// 透传核心 PDF 解析函数
// ---------------------------------------------------------------------------

/// 解析 PDF 文件（Stage 1）。
pub async fn parse_pdf(
    path: String,
    chunk_size: Option<usize>,
    overlap: Option<usize>,
    parser: Option<String>,
) -> Result<PdfParseResult, String> {
    crate::parsers::pipeline::parse_pdf(path, chunk_size, overlap, parser).await
}

/// 对解析结果进行后处理（LLM 结构化提取）。
pub fn post_process_pdf(parse_result: PdfParseResult) -> Result<PostProcessResult, String> {
    crate::parsers::pipeline::post_process_pdf(parse_result)
}

/// 处理单个文档（完整管线 Stage 0~7）。
pub async fn process_document(
    path: String,
    user_request: Option<String>,
    project_root: Option<String>,
    app: tauri::AppHandle,
) -> Result<(), String> {
    crate::parsers::pipeline::process_document(path, user_request, project_root, app).await
}

/// 批量索引项目下的所有 PDF 文件。
pub async fn index_project_rust(
    app: tauri::AppHandle,
    root: String,
) -> Result<IndexResult, String> {
    crate::parsers::pipeline::index_project_rust(app, root).await
}

/// PDF 分子提取工作流（完整封装）。
pub async fn extract_pdf_workflow(
    pdf_path: &str,
    output_dir: &str,
    sidecar_url: &str,
) -> Result<WorkflowResult, String> {
    crate::parsers::pipeline::extract_pdf_workflow(pdf_path, output_dir, sidecar_url).await
}

/// 分类并提取文件（自动检测 parser）。
///
/// `allow_ocr` 控制是否允许对扫描件调用 MinerU OCR。
/// Inspector 阶段和快速 MoldDet 扫描应传 `false`，避免在用户确认前跑 OCR。
pub async fn classify_and_extract(path: &str, allow_ocr: bool) -> Result<ClassifyResult, String> {
    crate::parsers::pipeline::classify_and_extract(path, allow_ocr).await
}

/// 查找项目根目录（通过向上搜索 .mbforge 目录）。
pub fn find_project_root(start: &Path, explicit: Option<&str>) -> Option<PathBuf> {
    crate::parsers::pipeline::find_project_root(start, explicit)
}

// ---------------------------------------------------------------------------
// 关联提取 facade — 底层调用在 commands/extractor.rs
// ---------------------------------------------------------------------------

/// 提取活性条目（delegate to parsers/association）。
pub fn extract_activities(text: &str) -> Vec<ActivityEntry> {
    crate::parsers::chem::association::extract_activities(text)
}
