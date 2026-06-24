// PDF inspection commands — Task 2: classify_pdf

use std::collections::{HashMap, HashSet};
use std::path::Path;

use chrono::Utc;
use lopdf::{Document, Object};
use pdf_inspector::{detect_pdf, process_pdf, PdfType};
use pdf_inspector::extractor::extract_text_with_positions_pages;
use serde::Serialize;
use serde_json::{from_str, from_value, json, to_string_pretty, Value};

pub use crate::core::document::ingest_queue::IngestStatus;
use crate::core::chem::chem::esmiles_to_molecode;
use crate::core::config::constants::PROJECTS_DIR;
use crate::core::constants::{PROJECT_META_DIR, sidecar_url};
use crate::core::document::ingest_queue::{IngestQueue, IngestTask, QueueStats};
use crate::core::error::AppError;
use crate::core::helpers::{assert_within_root_allow_missing, clean_path, generate_uuid, safe_join, save_json, sha256_file};
use crate::core::molecule::molecule_store::{MoleculeDatabase, MoleculeImage, MoleculeRecord};
use crate::core::project::document_project::DocumentProject;
use crate::core::project::project::Project;
use crate::parsers::chem::chem_validate::separate_esmiles_layers;
use crate::parsers::chem::label_assoc::{extract_page_text_lines, find_label_for_bbox, TextLine};
use crate::parsers::chem::vlm_chem::DetectedMolecule;
use crate::parsers::doc_types::{ImageRef as DocImageRef, OcrBlock as DocOcrBlock};
use crate::parsers::pipeline::context::PipelineContext;
use crate::parsers::pipeline::models::enriched::DetectedMoleculeResult;
use crate::parsers::pipeline::models::extracted::{ImageRef, OcrBlock};
use crate::parsers::pipeline::models::source::SourceInput;
use crate::parsers::pipeline::runner::Stage;
use crate::parsers::pipeline::services::molecules::MoleculeService;
use crate::parsers::pipeline::services::ocr::{default_backends, OcrService};
use crate::parsers::pipeline::services::ocr_layout::{get_ocr_layout, OcrLayoutBlock};
use crate::parsers::pipeline::services::source::SourceResolver;
use crate::parsers::pipeline::stages::extract::ExtractStage;
use crate::parsers::pipeline::writer::markdown_augment;

/// Classification result returned to the frontend via Tauri IPC.
///
/// This struct is intentionally kept lean — it carries only the fields
/// the frontend needs for routing (text vs scanned vs mixed) and for
/// displaying a progress / quality indicator.
#[derive(Debug, Serialize)]
pub struct PdfClassification {
    /// PDF type: "TextBased", "Scanned", "Mixed", or "ImageBased".
    pub pdf_type: String,
    /// Detection confidence (0.0–1.0).
    pub confidence: f64,
    /// Total number of pages.
    pub page_count: usize,
    /// 1-indexed page numbers that need OCR.
    pub pages_needing_ocr: Vec<usize>,
    /// Average text density across all pages (characters per square point).
    /// `0.0` when text extraction was not performed (detect-only mode).
    pub text_density_avg: f64,
    /// Whether any page has tables or multi-column layout.
    pub has_complex_layout: bool,
    /// `true` when broken font encodings are detected (garbled text).
    pub has_encoding_issues: bool,
    /// Title from PDF metadata (if available).
    pub title: Option<String>,
}

/// Tauri command: classify a PDF without full text extraction.
///
/// Uses `detect_pdf` (ProcessMode::DetectOnly) for fast
/// classification (~10–50ms).  The returned `PdfClassification` contains
/// the PDF type, per-page OCR needs, and layout / encoding diagnostics
/// that the frontend can surface to the user.
#[tauri::command]
pub fn classify_pdf(path: String) -> Result<PdfClassification, String> {
    let result = detect_pdf(&path).map_err(|e| {
        log::error!("classify_pdf failed for path={}: {}", path, e);
        format!("pdf-inspector detect failed: {}", e)
    })?;

    let pdf_type = match result.pdf_type {
        PdfType::TextBased => "TextBased",
        PdfType::Scanned => "Scanned",
        PdfType::Mixed => "Mixed",
        PdfType::ImageBased => "ImageBased",
    };

    log::info!(
        "classify_pdf: path={} type={} pages={} ocr={:?}",
        path,
        pdf_type,
        result.page_count,
        result.pages_needing_ocr
    );

    Ok(PdfClassification {
        pdf_type: pdf_type.to_string(),
        confidence: result.confidence as f64,
        page_count: result.page_count as usize,
        pages_needing_ocr: result
            .pages_needing_ocr
            .iter()
            .map(|&p| p as usize)
            .collect(),
        // text_density_avg requires full text extraction (ProcessMode::Full);
        // detect-only mode does not extract text, so this is 0.0 here.
        // The Python pipeline can compute a real value when it runs full extraction.
        text_density_avg: 0.0,
        has_complex_layout: result.layout.is_complex,
        has_encoding_issues: result.has_encoding_issues,
        title: result.title,
    })
}

// =========================================================================
// DocumentProject inspector + OCR confirmation
// =========================================================================

/// 快速检查 PDF 类型并写入 DocumentProject 状态。
///
/// 返回与 `classify_pdf` 相同的结构，但会：
/// 1. 从 `doc_id` 解析出 `projects/<doc_id>/source.pdf` 路径；
/// 2. 调用 `detect_pdf` 判定类型；
/// 3. 将结果写入 `projects/<doc_id>/cache/inspector.json`；
/// 4. 更新 DocumentProject / Project index 的 `inspector_status` 与 `ocr_status`。
#[tauri::command]
pub fn inspect_pdf(project_root: String, doc_id: String) -> Result<PdfClassification, String> {
    let root = assert_within_root_allow_missing(&clean_path(&project_root), Path::new("."))
        .map_err(|e| format!("Invalid project_root {}: {}", project_root, e))?;

    let project =
        Project::open(&root).ok_or_else(|| format!("Cannot open project at {}", project_root))?;
    let source_path = project
        .get_document_source_path(&doc_id)
        .ok_or_else(|| format!("Document {} source path not found", doc_id))?;

    let result =
        detect_pdf(source_path.to_string_lossy().as_ref()).map_err(|e| {
            log::error!("inspect_pdf failed for {}: {}", source_path.display(), e);
            // Best-effort: mark inspector status as error
            if let Some(mut dp) = DocumentProject::load(&root, &doc_id) {
                dp.set_inspector_status("error");
            }
            if let Some(mut proj) = Project::open(&root) {
                proj.set_document_status(&doc_id, "inspector_status", "error");
            }
            format!("pdf-inspector detect failed: {}", e)
        })?;

    let pdf_type_str = match result.pdf_type {
        PdfType::TextBased => "TextBased",
        PdfType::Scanned => "Scanned",
        PdfType::Mixed => "Mixed",
        PdfType::ImageBased => "ImageBased",
    };

    // Persist inspector result to the DocumentProject cache.
    let inspector_json = json!({
        "pdf_type": pdf_type_str,
        "confidence": result.confidence,
        "page_count": result.page_count,
        "pages_needing_ocr": result.pages_needing_ocr,
        "has_complex_layout": result.layout.is_complex,
        "has_encoding_issues": result.has_encoding_issues,
        "title": result.title,
        "inspected_at": Utc::now().to_rfc3339(),
    });
    if let Some(mut dp) = DocumentProject::load(&root, &doc_id) {
        let paths = dp.paths();
        if let Err(e) = std::fs::create_dir_all(&paths.cache_dir) {
            log::warn!(
                "Failed to create cache dir {} for doc {}: {}",
                paths.cache_dir.display(),
                doc_id,
                e
            );
        }
        match safe_join(&paths.cache_dir, "inspector.json") {
            Ok(inspector_path) => {
                if let Err(e) = save_json(&inspector_path, &inspector_json) {
                    log::warn!(
                        "Failed to save inspector json {} for doc {}: {}",
                        inspector_path.display(),
                        doc_id,
                        e
                    );
                }
            }
            Err(e) => {
                log::warn!(
                    "Invalid inspector cache path under {} for doc {}: {}",
                    paths.cache_dir.display(),
                    doc_id,
                    e
                );
            }
        }

        // Update DocumentProject statuses.
        dp.set_inspector_status(pdf_type_str.to_lowercase().as_str());
        match result.pdf_type {
            PdfType::TextBased => {
                dp.set_text_status("pending");
                dp.set_ocr_status("not_needed");
            }
            _ => {
                dp.set_text_status("pending");
                dp.set_ocr_status("pending_confirmation");
            }
        }
    }

    // Also mirror to the lightweight Project index.
    if let Some(mut proj) = Project::open(&root) {
        proj.set_document_status(&doc_id, "inspector_status", &pdf_type_str.to_lowercase());
        let ocr_status = match result.pdf_type {
            PdfType::TextBased => "not_needed",
            _ => "pending_confirmation",
        };
        proj.set_document_status(&doc_id, "ocr_status", ocr_status);
    }

    log::info!(
        "inspect_pdf: doc_id={} type={} pages={} ocr={:?}",
        doc_id,
        pdf_type_str,
        result.page_count,
        result.pages_needing_ocr
    );

    Ok(PdfClassification {
        pdf_type: pdf_type_str.to_string(),
        confidence: result.confidence as f64,
        page_count: result.page_count as usize,
        pages_needing_ocr: result
            .pages_needing_ocr
            .iter()
            .map(|&p| p as usize)
            .collect(),
        text_density_avg: 0.0,
        has_complex_layout: result.layout.is_complex,
        has_encoding_issues: result.has_encoding_issues,
        title: result.title,
    })
}

/// 用户确认/跳过扫描件 OCR。
///
/// - `confirm = true`：将 OCR 状态设为 `pending`，并把任务加入 ingest queue。
/// - `confirm = false`：将 OCR 状态设为 `skipped`，后续只处理可提取文本。
#[tauri::command]
pub async fn confirm_ocr(
    project_root: String,
    doc_id: String,
    confirm: bool,
) -> Result<Value, String> {
    let root = assert_within_root_allow_missing(&clean_path(&project_root), Path::new("."))
        .map_err(|e| format!("Invalid project_root {}: {}", project_root, e))?;

    let project =
        Project::open(&root).ok_or_else(|| format!("Cannot open project at {}", project_root))?;
    let source_path = project
        .get_document_source_path(&doc_id)
        .ok_or_else(|| format!("Document {} source path not found", doc_id))?;

    let status = if confirm { "pending" } else { "skipped" };

    // Update DocumentProject
    if let Some(mut dp) = DocumentProject::load(&root, &doc_id) {
        dp.set_ocr_status(status);
    }

    // Update Project index
    if let Some(mut proj) = Project::open(&root) {
        proj.set_document_status(&doc_id, "ocr_status", status);
    }

    // Enqueue OCR task if confirmed (worker will consume it in Phase 3).
    let task_id = if confirm {
        let q = IngestQueue::new(&root)
            .map_err(|e| format!("Failed to open ingest queue: {}", e))?;
        q.enqueue_with_stage(
            source_path.to_string_lossy().to_string(),
            doc_id.clone(),
            "ocr",
            false,
        )
        .await
        .map_err(|e| format!("Failed to enqueue OCR task: {}", e))?
    } else {
        String::new()
    };

    log::info!(
        "confirm_ocr: doc_id={} confirm={} status={} task_id={}",
        doc_id,
        confirm,
        status,
        if task_id.is_empty() { "none" } else { &task_id }
    );

    Ok(json!({
        "success": true,
        "doc_id": doc_id,
        "ocr_status": status,
        "task_id": task_id,
    }))
}

// =========================================================================
// Task 3: extract_text
// =========================================================================

/// Extraction result returned to the frontend via Tauri IPC.
#[derive(Debug, Serialize)]
pub struct PdfExtraction {
    /// Structured Markdown output (headings, tables, lists).
    pub markdown: String,
    /// Total page count.
    pub page_count: usize,
    /// 1-indexed page numbers that need OCR.
    pub pages_needing_ocr: Vec<usize>,
    /// Detection confidence (0.0–1.0).
    pub confidence: f32,
    /// Whether any page has tables or multi-column layout.
    pub has_complex_layout: bool,
    /// `true` when broken font encodings are detected.
    pub has_encoding_issues: bool,
}

/// Tauri command: extract structured Markdown from a PDF.
///
/// Uses `process_pdf` (ProcessMode::Full) for complete
/// extraction including text, tables, and layout detection.
#[tauri::command]
pub fn extract_text(path: String) -> Result<PdfExtraction, String> {
    let result = process_pdf(&path).map_err(|e| {
        log::error!("extract_text failed for path={}: {}", path, e);
        format!("pdf-inspector process failed: {}", e)
    })?;

    log::info!(
        "extract_text: path={} pages={} ocr={:?}",
        path,
        result.page_count,
        result.pages_needing_ocr
    );

    Ok(PdfExtraction {
        // An empty markdown field just means no text was recovered; default is safe.
        markdown: result.markdown.unwrap_or_default(),
        page_count: result.page_count as usize,
        pages_needing_ocr: result
            .pages_needing_ocr
            .iter()
            .map(|&p| p as usize)
            .collect(),
        confidence: result.confidence,
        has_complex_layout: result.layout.is_complex,
        has_encoding_issues: result.has_encoding_issues,
    })
}

// =========================================================================
// PDF 分子提取工作流
// =========================================================================

/// 工作流输出结果（与 legacy 保持同构，供前端消费）。
#[derive(Debug, serde::Serialize)]
pub struct WorkflowResult {
    /// 输出目录
    pub output_dir: String,
    /// 文本文件路径
    pub text_path: String,
    /// manifest.json 路径
    pub manifest_path: String,
    /// 提取结果（文本、页数、解析器、图片引用）
    pub classify: ClassifyResult,
    /// 检测到的分子列表
    pub molecules: Vec<DetectedMolecule>,
}

/// 分类提取结果（与 legacy 同构）。
#[derive(Debug, serde::Serialize)]
pub struct ClassifyResult {
    pub text: String,
    pub page_count: usize,
    pub parser: String,
    pub images: Vec<DocImageRef>,
    pub ocr_blocks: Vec<DocOcrBlock>,
}

/// 单个分子的元数据（写入 manifest.json）。
#[derive(Debug, serde::Serialize)]
struct MoleculeEntry {
    index: usize,
    smiles: String,
    esmiles: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    molcode: Option<String>,
    name: String,
    page: i32,
    moldet_confidence: f64,
    molscribe_confidence: f64,
    image_file: String,
}

/// manifest.json 结构
#[derive(Debug, serde::Serialize)]
struct Manifest {
    source: String,
    parser: String,
    page_count: usize,
    text_file: String,
    molecules: Vec<MoleculeEntry>,
}

/// Tauri 命令：完整的 PDF 分子提取工作流。
///
/// 输入 PDF → 提取文本 + 检测分子图片 + 识别 SMILES → 输出到指定目录 + 写入 SQLite。
///
/// 输出结构（写入项目根目录下的规范位置，不再使用 `output_dir`）:
/// ```text
/// <output_dir>/
///   <pdf_name>/text.md
///   <pdf_name>/molecules/manifest.json
///   <pdf_name>/molecules/<pdf_name>/page_*_mol_*.png
/// ```
///
/// `output_dir` 仍作为入参保留（向后兼容）。管线 v2 负责文本提取与分子识别；
/// 本命令仅把 v2 产物整理成前端期望的 `WorkflowResult` 结构。
#[tauri::command]
pub async fn extract_pdf_workflow_cmd(
    path: String,
    output_dir: String,
) -> Result<WorkflowResult, String> {
    let sidecar_url = sidecar_url();
    let source_path = Path::new(&path);

    // Validate output_dir as the safe root for all generated workflow files.
    let output_root = assert_within_root_allow_missing(&clean_path(&output_dir), Path::new("."))
        .map_err(|e| format!("Invalid output_dir {}: {}", output_dir, e))?;
    let output_root_str = output_root.to_string_lossy().to_string();

    let pdf_name = source_path
        .file_stem()
        .map(|n| n.to_string_lossy().to_string())
        .unwrap_or_else(|| "output".to_string()); // Fallback stem when the source path has no usable filename.

    // Build validated paths under output_root before any filesystem mutation.
    let base_dir = assert_within_root_allow_missing(&output_root_str, Path::new(&pdf_name))
        .map_err(|e| format!("Invalid workflow base dir under {}: {}", output_root.display(), e))?;
    let mol_dir = assert_within_root_allow_missing(
        &base_dir.to_string_lossy(),
        Path::new("molecules"),
    )
    .map_err(|e| format!("Invalid molecules dir under {}: {}", base_dir.display(), e))?;
    std::fs::create_dir_all(&mol_dir)
        .map_err(|e| format!("Failed to create output dir: {}", e))?;

    // 工作根目录：管线 v2 的提取/识别产物都落到 <output_dir>/<pdf_name>/ 下，
    // 与 legacy extract_pdf_workflow 的 on-disk 布局保持一致。
    let work_root = base_dir.clone();

    // 真正的项目根（用于 SQLite 分子库），优先从 PDF 路径推导，其次 output_dir。
    let project_root =
        match SourceResolver::new().resolve_project_root(source_path, Some(&output_root)) {
            Ok(root) => {
                let root = assert_within_root_allow_missing(&root.to_string_lossy(), Path::new("."))
                    .map_err(|e| {
                        format!("Resolved project root {} is invalid: {}", root.display(), e)
                    })?;
                Some(root)
            }
            Err(e) => {
                log::warn!(
                    "[workflow] Failed to resolve project root from PDF path {}: {}",
                    path,
                    e
                );
                log::warn!(
                    "[workflow] Falling back to output_dir as project root: {}",
                    output_root.display()
                );
                Some(output_root.clone())
            }
        };

    log::info!(
        "[workflow] Starting v2 extraction: {} → {}",
        path,
        base_dir.display()
    );

    // Stage 1: 文本提取 + 分类（v2 ExtractStage）
    let ctx = PipelineContext::new(source_path, "").with_project_root(&work_root);
    let ocr = OcrService::new(default_backends());
    let extract_stage = ExtractStage::new(ocr);
    let extracted = extract_stage
        .run(SourceInput::new(source_path).with_project_root(&work_root), &ctx)
        .await
        .map_err(|e| format!("Extract stage failed: {}", e))?
        .output;

    // 把 v2 模型类型转成 doc_types 类型以复用 markdown_augment。
    let images_doc: Vec<DocImageRef> = extracted.images.iter().cloned().map(into_doc_image_ref).collect();
    let ocr_blocks_doc: Vec<DocOcrBlock> = extracted
        .ocr_blocks
        .iter()
        .cloned()
        .map(into_doc_ocr_block)
        .collect();

    let augmented_text = markdown_augment::augment_markdown_with_images(
        &extracted.raw_text,
        &images_doc,
        Some(&ocr_blocks_doc),
    );

    let text_path = safe_join(&base_dir, "text.md")
        .map_err(|e| format!("Invalid text.md path under {}: {}", base_dir.display(), e))?;
    std::fs::write(&text_path, &augmented_text)
        .map_err(|e| format!("Failed to write text.md: {}", e))?;

    log::info!(
        "[workflow] Text extracted: {} pages, {} chars, parser={}",
        extracted.page_count,
        extracted.raw_text.len(),
        extracted.parser
    );

    // Stage 2: 分子图像检测 + 识别（v2 MoleculeService）
    let detected = if let Some(ref root) = project_root {
        let mol_service = MoleculeService::new(&sidecar_url);
        mol_service
            .extract(&path, &extracted, root)
            .await
            .unwrap_or_else(|e| {
                // Continue the workflow even if molecule recognition fails;
                // the text/markdown output is still valuable on its own.
                log::warn!("[workflow] Molecule extraction failed: {}", e);
                Vec::new()
            })
    } else {
        Vec::new()
    };

    let legacy_molecules: Vec<DetectedMolecule> = detected
        .iter()
        .map(into_legacy_molecule)
        .collect();

    log::info!("[workflow] Detected {} molecules", legacy_molecules.len());

    // Stage 3: 生成 manifest.json
    let molecules: Vec<MoleculeEntry> = legacy_molecules
        .iter()
        .enumerate()
        .map(|(i, mol)| {
            let image_file = Path::new(&mol.crop_path)
                .file_name()
                .map(|n| n.to_string_lossy().to_string())
                .unwrap_or_else(|| format!("page_{:04}_mol_{:03}.png", mol.page, i)); // Fallback filename preserves page/index if crop path is missing.
            let (smiles, esmiles_opt, _tags) = separate_esmiles_layers(&mol.esmiles);
            let mol_name = format!("IMG-{}-P{}", pdf_name, mol.page);
            let molcode = esmiles_opt
                .as_deref()
                .unwrap_or(&smiles) // Use canonical SMILES when no E-SMILES layer is present.
                .trim()
                .is_empty()
                .then(|| None)
                .unwrap_or_else(|| esmiles_to_molecode_opt(esmiles_opt.as_deref().unwrap_or(&smiles), &mol_name));
            MoleculeEntry {
                index: i,
                smiles,
                esmiles: esmiles_opt,
                molcode,
                name: mol_name,
                page: mol.page,
                moldet_confidence: mol.moldet_conf,
                molscribe_confidence: mol.confidence,
                image_file,
            }
        })
        .collect();

    let manifest = Manifest {
        source: pdf_name.clone(),
        parser: extracted.parser.clone(),
        page_count: extracted.page_count,
        text_file: "text.md".to_string(),
        molecules,
    };

    let manifest_path = safe_join(&mol_dir, "manifest.json")
        .map_err(|e| format!("Invalid manifest path under {}: {}", mol_dir.display(), e))?;
    let manifest_json = to_string_pretty(&manifest)
        .map_err(|e| format!("Failed to serialize manifest: {}", e))?;
    std::fs::write(&manifest_path, manifest_json)
        .map_err(|e| format!("Failed to write manifest.json: {}", e))?;

    // Stage 4: 将检测到的分子写入 SQLite（molecules + molecule_images）
    if !legacy_molecules.is_empty() {
        if let Some(ref root) = project_root {
            match MoleculeDatabase::open(root) {
                Ok(db) => {
                    let mut lines_cache: HashMap<i32, Vec<TextLine>> = HashMap::new();
                    // Default to A4 height (842 pt) for coordinate conversion if PDF page metadata is unavailable.
                    let page_h_pts = get_page_height(&path).unwrap_or(842.0);

                    let mut saved = 0usize;
                    for (idx, mol) in legacy_molecules.iter().enumerate() {
                        let (clean_smiles, esmiles_opt, semantic_tags) =
                            separate_esmiles_layers(&mol.esmiles);

                        let page_num = (mol.page).max(0);
                        let lines = lines_cache.entry(page_num).or_insert_with(|| {
                            match extract_page_text_lines(
                                &path,
                                page_num as u32,
                                page_h_pts,
                            ) {
                                Ok(lines) => lines,
                                Err(e) => {
                                    log::warn!(
                                        "[extract_workflow] page {} text extraction failed: {}",
                                        page_num,
                                        e
                                    );
                                    Vec::new()
                                }
                            }
                        });
                        let label_match = if mol.bbox_pdf != [0.0, 0.0, 0.0, 0.0] {
                            find_label_for_bbox(
                                (
                                    mol.bbox_pdf[0],
                                    mol.bbox_pdf[1],
                                    mol.bbox_pdf[2],
                                    mol.bbox_pdf[3],
                                ),
                                lines,
                                page_h_pts,
                                80.0,
                            )
                        } else {
                            None
                        };
                        let resolved_name = match &label_match {
                            Some(m) => m.label.clone(),
                            None => format!("IMG-{}-P{:03}-{:03}", pdf_name, mol.page, idx),
                        };
                        let mut properties = json!({});
                        if let Some(m) = &label_match {
                            properties["context_text"] =
                                Value::String(m.context_text.clone());
                        }
                        properties["bbox_pdf"] = json!(mol.bbox_pdf);

                        let mol_id = generate_uuid();
                        let record = MoleculeRecord {
                            mol_id: mol_id.clone(),
                            smiles: clean_smiles,
                            esmiles: esmiles_opt,
                            semantic_tags,
                            name: resolved_name,
                            source_doc: pdf_name.clone(),
                            activity: None,
                            activity_type: String::new(),
                            units: "nM".to_string(),
                            source_type: "workflow_extract".to_string(),
                            status: "pending".to_string(),
                            properties,
                            labels: vec!["image_extracted".to_string()],
                            notes: format!(
                                "Workflow extract: MolDet (conf={:.2}) + MolScribe (conf={:.2})",
                                mol.moldet_conf, mol.confidence
                            ),
                            created_at: None,
                            related_image_paths: vec![mol.crop_path.clone()],
                            vlm_verified_esmiles: Some(mol.esmiles.clone()),
                            vlm_confidence: mol.confidence,
                        };
                        if let Err(e) = db.add_molecule(&record) {
                            log::warn!(
                                "[extract_workflow] Failed to add molecule {}: {}",
                                mol_id,
                                e
                            );
                        } else {
                            let img = MoleculeImage {
                                image_id: generate_uuid(),
                                mol_id: mol_id.clone(),
                                image_path: mol.crop_path.clone(),
                                page: Some(mol.page as usize),
                                vlm_esmiles: Some(mol.esmiles.clone()),
                                vlm_confidence: mol.confidence,
                                is_structure_diagram: true,
                                created_at: None,
                                bbox_in_image: None,
                                moldet_conf: None,
                            };
                            if let Err(e) = db.add_molecule_image(&img) {
                                log::warn!("[extract_workflow] Failed to add image: {}", e);
                            } else {
                                saved += 1;
                            }
                        }
                    }
                    log::info!(
                        "[extract_workflow] Persisted {}/{} molecules to DB",
                        saved,
                        legacy_molecules.len()
                    );
                }
                Err(e) => {
                    log::warn!(
                        "[workflow] Failed to open molecule database at {}: {}",
                        root.display(),
                        e
                    );
                }
            }
        }
    }

    let classify = ClassifyResult {
        text: extracted.raw_text,
        page_count: extracted.page_count,
        parser: extracted.parser,
        images: images_doc,
        ocr_blocks: ocr_blocks_doc,
    };

    let result = WorkflowResult {
        output_dir: base_dir.to_string_lossy().to_string(),
        text_path: text_path.to_string_lossy().to_string(),
        manifest_path: manifest_path.to_string_lossy().to_string(),
        classify,
        molecules: legacy_molecules,
    };

    log::info!(
        "[workflow] Done: {} pages, {} molecules → {}",
        result.classify.page_count,
        result.molecules.len(),
        result.output_dir
    );

    Ok(result)
}

/// Best-effort wrapper around `esmiles_to_molecode` for the manifest
/// generation path. Returns `None` on parse failure or empty input so
/// the rest of `MoleculeEntry` is still useful.
fn esmiles_to_molecode_opt(input: &str, name: &str) -> Option<String> {
    let trimmed = input.trim();
    if trimmed.is_empty() {
        return None;
    }
    match esmiles_to_molecode(trimmed, name) {
        Ok(r) => Some(r.mermaid),
        Err(e) => {
            log::warn!(
                "[molcode] esmiles_to_molecode failed for {} ({} chars): {}",
                name,
                trimmed.len(),
                e
            );
            None
        }
    }
}

fn into_legacy_molecule(
    m: &DetectedMoleculeResult,
) -> DetectedMolecule {
    DetectedMolecule {
        esmiles: m.esmiles.clone(),
        confidence: m.confidence,
        moldet_conf: m.moldet_conf,
        page: m.page as i32,
        crop_path: m.crop_path.clone(),
        bbox_pdf: m.bbox_pdf,
    }
}

fn into_doc_image_ref(
    img: ImageRef,
) -> DocImageRef {
    DocImageRef {
        filename: img.filename,
        page: img.page,
        region: img.region,
        description: img.description,
        esmiles: img.esmiles,
        rel_path: img.rel_path,
    }
}

fn into_doc_ocr_block(
    block: OcrBlock,
) -> DocOcrBlock {
    DocOcrBlock {
        page: block.page,
        block_type: block.block_type,
        bbox: block.bbox,
        content: block.content,
        index: block.index,
        angle: block.angle,
    }
}

// =========================================================================
// OCR 布局可视化
// =========================================================================

/// OCR 布局结果返回给前端
#[derive(Debug, Serialize)]
pub struct OcrLayoutResult {
    /// 文档路径
    pub path: String,
    /// 使用的解析器
    pub parser: String,
    /// 总页数
    pub page_count: usize,
    /// OCR 布局块列表
    pub blocks: Vec<DocOcrBlock>,
    /// 是否来自缓存
    pub from_cache: bool,
}

/// Tauri 命令：获取文档的 OCR 布局数据（用于可视化）。
///
/// 优先从 OCR 缓存读取；如果没有缓存且文档需要 MinerU 解析，
/// 则调用 v2 `get_ocr_layout` 获取（不写入缓存）。
/// 若提供 doc_id，会在处理前后更新项目 index 中的 ocr_status。
#[tauri::command]
pub async fn get_document_ocr_layout(
    path: String,
    doc_id: Option<String>,
) -> Result<OcrLayoutResult, String> {
    let source_path = Path::new(&path);
    let project_root = SourceResolver::new()
        .resolve_project_root(source_path, None)
        .ok()
        .and_then(|root| {
            match assert_within_root_allow_missing(&root.to_string_lossy(), Path::new(".")) {
                Ok(validated) => Some(validated),
                Err(e) => {
                    log::warn!("Resolved project root {} is invalid: {}", root.display(), e);
                    None
                }
            }
        });
    let file_hash = match sha256_file(source_path) {
        Ok(hash) => hash,
        Err(e) => {
            log::warn!("Failed to compute file hash for {}: {}", path, e);
            String::new()
        }
    };

    // 辅助：更新 OCR 状态
    let update_status = |status: &str| {
        if let (Some(root), Some(id)) = (&project_root, &doc_id) {
            if let Some(mut project) = Project::open(root) {
                project.set_document_ocr(id, status, &file_hash);
            }
        }
    };

    // 1. 尝试从缓存读取。
    //    新布局优先读取 projects/<doc_id>/cache/ocr/ocr.json，再回退到旧版
    //    .mbforge/ocr-cache/<hash>.json。
    if let Some(ref root) = project_root {
        // 1a. DocumentProject 新路径
        if let Some(ref id) = doc_id {
            let root_str = root.to_string_lossy().to_string();
            let new_cache_rel = format!("{}/{}/cache/ocr/ocr.json", PROJECTS_DIR, id);
            let new_cache = assert_within_root_allow_missing(&root_str, Path::new(&new_cache_rel))
                .map_err(|e| format!("Invalid OCR cache path: {}", e))?;
            if new_cache.exists() {
                match std::fs::read_to_string(&new_cache) {
                    Ok(content) => {
                        match from_str::<Value>(&content) {
                            Ok(val) => {
                                let text = val["text"].as_str().unwrap_or("").to_string(); // Empty text is a safe default for a stale/malformed cache entry.
                                let page_count = val["page_count"]
                                    .as_u64()
                                    .map(|n| n as usize)
                                    .unwrap_or_else(|| text.lines().count().max(1)); // Infer from cached text, ensuring at least one page.
                                let blocks: Vec<DocOcrBlock> = val["ocr_blocks"]
                                    .as_array()
                                    .map(|arr| {
                                        arr.iter()
                                            .filter_map(|v| from_value(v.clone()).ok())
                                            .collect()
                                    })
                                    .unwrap_or_default(); // Missing block array defaults to empty; will fall through to live extraction.
                                let parser = val["parser"].as_str().unwrap_or("unknown").to_string(); // Unknown parser for stale/malformed cache entries.
                                if !blocks.is_empty() {
                                    log::info!(
                                        "OCR layout cache HIT (new) for {}: {} blocks",
                                        path,
                                        blocks.len()
                                    );
                                    update_status("completed");
                                    return Ok(OcrLayoutResult {
                                        path: path.clone(),
                                        parser,
                                        page_count,
                                        blocks,
                                        from_cache: true,
                                    });
                                }
                            }
                            Err(e) => {
                                log::debug!(
                                    "Failed to parse OCR layout cache (new) {}: {}",
                                    new_cache.display(),
                                    e
                                );
                            }
                        }
                    }
                    Err(e) => {
                        log::debug!(
                            "Failed to read OCR layout cache (new) {}: {}",
                            new_cache.display(),
                            e
                        );
                    }
                }
            }
        }

        // 1b. 旧版按 hash 的缓存
        let root_str = root.to_string_lossy().to_string();
        let cache_file_rel = format!("{}/ocr-cache/{}.json", PROJECT_META_DIR, file_hash);
        let cache_file = assert_within_root_allow_missing(&root_str, Path::new(&cache_file_rel))
            .map_err(|e| format!("Invalid OCR cache path: {}", e))?;
        if cache_file.exists() {
            match std::fs::read_to_string(&cache_file) {
                Ok(content) => {
                    match from_str::<Value>(&content) {
                        Ok(val) => {
                            let text = val["text"].as_str().unwrap_or("").to_string(); // Empty text is a safe default for a stale/malformed cache entry.
                            let page_count = text.lines().count().max(1); // Infer from cached text, ensuring at least one page.
                            let blocks: Vec<DocOcrBlock> = val["ocr_blocks"]
                                .as_array()
                                .map(|arr| {
                                    arr.iter()
                                        .filter_map(|v| from_value(v.clone()).ok())
                                        .collect()
                                })
                                .unwrap_or_default(); // Missing block array defaults to empty; will fall through to live extraction.
                            let parser = val["parser"].as_str().unwrap_or("unknown").to_string(); // Unknown parser for stale/malformed cache entries.
                            if !blocks.is_empty() {
                                log::info!("OCR layout cache HIT for {}: {} blocks", path, blocks.len());
                                update_status("completed");
                                return Ok(OcrLayoutResult {
                                    path: path.clone(),
                                    parser,
                                    page_count,
                                    blocks,
                                    from_cache: true,
                                });
                            }
                        }
                        Err(e) => {
                            log::debug!(
                                "Failed to parse OCR layout cache {}: {}",
                                cache_file.display(),
                                e
                            );
                        }
                    }
                }
                Err(e) => {
                    log::debug!(
                        "Failed to read OCR layout cache {}: {}",
                        cache_file.display(),
                        e
                    );
                }
            }
        }
    }

    // 2. 缓存未命中：调用 v2 OCR layout service 获取
    log::info!("OCR layout cache MISS for {}, running extraction...", path);
    update_status("processing");

    let ctx = match project_root {
        Some(ref root) => PipelineContext::new(source_path, "").with_project_root(root),
        None => PipelineContext::new(source_path, ""),
    };
    let result = get_ocr_layout(source_path, &ctx).await;

    match result {
        Ok(blocks) => {
            let has_blocks = !blocks.is_empty();
            update_status(if has_blocks {
                "completed"
            } else {
                "not_processed"
            });
            // At least one page if any blocks exist; an empty layout still reports one page.
            let page_count = blocks.iter().map(|b| b.page).max().unwrap_or(1);
            Ok(OcrLayoutResult {
                path: path.clone(),
                parser: "ocr_layout".to_string(),
                page_count,
                blocks: blocks.into_iter().map(into_doc_ocr_block_from_layout).collect(),
                from_cache: false,
            })
        }
        Err(e) => {
            update_status("error");
            Err(e)
        }
    }
}

fn into_doc_ocr_block_from_layout(
    block: OcrLayoutBlock,
) -> DocOcrBlock {
    DocOcrBlock {
        page: block.page,
        block_type: block.block_type,
        bbox: block.bbox,
        content: block.content,
        index: block.index,
        angle: block.angle,
    }
}

/// 从 PDF 第一页拿页面高度（点单位）。仅用于 label 关联时的坐标转换。
/// 拿不到时返回 842.0（A4 高度）。
fn get_page_height(pdf_path: &str) -> Option<f64> {
    let mut first_page: HashSet<u32> = HashSet::new();
    first_page.insert(1);
    if let Err(e) =
        extract_text_with_positions_pages(pdf_path, Some(&first_page))
    {
        log::warn!("Failed to extract text positions from {}: {}", pdf_path, e);
        return None;
    }
    // 走 Document API 拿页面尺寸
    let doc = match Document::load(pdf_path) {
        Ok(d) => d,
        Err(e) => {
            log::warn!("Failed to load PDF {}: {}", pdf_path, e);
            return None;
        }
    };
    let pages = doc.get_pages();
    let first_id = *pages.values().next()?;
    let page_dict = match doc.get_dictionary(first_id) {
        Ok(d) => d,
        Err(e) => {
            log::warn!("Failed to get first page dictionary for {}: {}", pdf_path, e);
            return None;
        }
    };
    let media_box = match page_dict.get(b"MediaBox") {
        Ok(m) => m,
        Err(e) => {
            log::warn!("Failed to get MediaBox for {}: {}", pdf_path, e);
            return None;
        }
    };
    let arr = match media_box.as_array() {
        Ok(a) => a,
        Err(e) => {
            log::warn!("MediaBox is not an array for {}: {}", pdf_path, e);
            return None;
        }
    };
    if arr.len() < 4 {
        log::warn!("MediaBox has fewer than 4 entries for {}", pdf_path);
        return None;
    }
    let h = match &arr[3] {
        Object::Real(r) => *r as f64,
        Object::Integer(i) => *i as f64,
        _ => {
            log::warn!("MediaBox height is not a numeric value for {}", pdf_path);
            return None;
        }
    };
    Some(h)
}

/// 把识别出的图像插入到 markdown：内联引用 + 末尾"## Extracted Images"。
/// pipeline 内部不再调用，留给前端需要"图 + 文字"合成展示时按需触发。
#[tauri::command]
pub fn augment_markdown_with_images(
    markdown: String,
    images: Vec<DocImageRef>,
    ocr_blocks: Option<Vec<DocOcrBlock>>,
) -> String {
    markdown_augment::augment_markdown_with_images(
        &markdown,
        &images,
        ocr_blocks.as_deref(),
    )
}

// ─── Figure bbox on PDF page（coref overlay 投影用） ────────────────

/// 一页内一个嵌入图的 on-page bbox（PDF points，左下原点）。
#[derive(Debug, Clone, Serialize)]
pub struct FigureBbox {
    /// PyMuPDF xref（同一 image 被多次引用时合并为并集 bbox）
    pub xref: u32,
    /// [x1, y1, x2, y2] in PDF points (bottom-left origin)
    pub bbox_pdf: [f64; 4],
    /// 原图 width (pixels)
    pub width: Option<u32>,
    /// 原图 height (pixels)
    pub height: Option<u32>,
}

/// 一页的 figures
#[derive(Debug, Clone, Serialize)]
pub struct PageFigureBboxes {
    pub page_num: u32,
    pub figures: Vec<FigureBbox>,
}

/// 返回整个 PDF 中所有嵌入图在各自页面上的 bbox（PyMuPDF 通过 sidecar）。
///
/// 用于 coref overlay 把 `figure_labels.label_bbox`（figure 内归一化 0-1）
/// 投影到 PDF 页面坐标系（与 MoleculeOverlay / OcrOverlay 同一坐标系）。
#[tauri::command]
pub async fn get_figure_bboxes(pdf_path: String) -> Result<Vec<PageFigureBboxes>, String> {
    let url = format!("{}/api/v1/pdf/figure-bboxes", sidecar_url());
    let body = serde_json::json!({ "pdf_path": pdf_path });
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(60))
        .build()
        .map_err(|e| format!("reqwest build failed: {e}"))?;
    let resp = client
        .post(&url)
        .json(&body)
        .send()
        .await
        .map_err(|e| format!("sidecar unreachable: {e}"))?;
    if !resp.status().is_success() {
        let status = resp.status();
        let text = resp.text().await.unwrap_or_default();
        return Err(format!("sidecar figure-bboxes HTTP {}: {}", status, text));
    }
    let raw: serde_json::Value = resp
        .json()
        .await
        .map_err(|e| format!("invalid JSON from sidecar: {e}"))?;

    let mut out = Vec::new();
    if let Some(pages) = raw.get("pages").and_then(|p| p.as_array()) {
        for page in pages {
            let page_num = page
                .get("page_num")
                .and_then(|n| n.as_u64())
                .unwrap_or(0) as u32;
            let mut figures = Vec::new();
            if let Some(arr) = page.get("figures").and_then(|f| f.as_array()) {
                for fig in arr {
                    let xref = fig.get("xref").and_then(|x| x.as_u64()).unwrap_or(0) as u32;
                    let bbox = fig
                        .get("bbox_pdf")
                        .and_then(|b| b.as_array())
                        .and_then(|arr| {
                            if arr.len() != 4 {
                                return None;
                            }
                            Some([
                                arr[0].as_f64()?,
                                arr[1].as_f64()?,
                                arr[2].as_f64()?,
                                arr[3].as_f64()?,
                            ])
                        })
                        .unwrap_or([0.0, 0.0, 0.0, 0.0]);
                    let width = fig.get("width").and_then(|w| w.as_u64()).map(|v| v as u32);
                    let height = fig.get("height").and_then(|h| h.as_u64()).map(|v| v as u32);
                    figures.push(FigureBbox { xref, bbox_pdf: bbox, width, height });
                }
            }
            out.push(PageFigureBboxes { page_num, figures });
        }
    }
    Ok(out)
}

// ─── IngestQueue：PDF 异步处理队列 ────────────────────────────────

fn open_ingest_queue(project_root: &str) -> Result<IngestQueue, String> {
    let root = assert_within_root_allow_missing(&clean_path(project_root), Path::new("."))
        .map_err(|e| format!("Invalid project_root {}: {}", project_root, e))?;
    IngestQueue::new(&root)
        .map_err(|e: AppError| e.to_string())
}

/// 入队一个 PDF 供异步处理。返回任务 ID。
///
/// `force=true` 时跳过同 hash 幂等检查 — 用于对已索引文件强制重新入队，
/// 新建任务而不复用现有 done 任务，保留历史记录。
#[tauri::command]
pub async fn ingest_enqueue(
    project_root: String,
    file_path: String,
    doc_id: String,
    force: Option<bool>,
) -> Result<String, String> {
    let q = open_ingest_queue(&project_root)?;
    q.enqueue_with_stage(
        file_path,
        doc_id,
        "inspector",
        force.unwrap_or(false), // Default to idempotent enqueue (skip duplicate done tasks).
    )
    .await
    .map_err(|e| e.to_string())
}

/// 列出队列中所有任务。
#[tauri::command]
pub async fn ingest_list(project_root: String) -> Result<Vec<IngestTask>, String> {
    let q = open_ingest_queue(&project_root)?;
    q.list_all().await.map_err(|e| e.to_string())
}

/// 队列统计：pending / running / done / failed 各多少。
#[tauri::command]
pub async fn ingest_stats(project_root: String) -> Result<QueueStats, String> {
    let q = open_ingest_queue(&project_root)?;
    q.stats().await.map_err(|e| e.to_string())
}

/// 取消单个任务。
#[tauri::command]
pub async fn ingest_cancel(project_root: String, task_id: String) -> Result<(), String> {
    let q = open_ingest_queue(&project_root)?;
    q.cancel(&task_id).await.map_err(|e| e.to_string())
}

/// 重试一个失败任务。
#[tauri::command]
pub async fn ingest_retry(project_root: String, task_id: String) -> Result<bool, String> {
    let q = open_ingest_queue(&project_root)?;
    q.retry(&task_id).await.map_err(|e| e.to_string())
}

/// 取消所有 pending 任务。返回被取消的数量。
#[tauri::command]
pub async fn ingest_cancel_all_pending(project_root: String) -> Result<usize, String> {
    let q = open_ingest_queue(&project_root)?;
    q.cancel_all_pending().await.map_err(|e| e.to_string())
}

/// 清理已完成/已取消/已失败的任务（保留 pending 与 running）。返回清理数量。
#[tauri::command]
pub async fn ingest_cleanup(project_root: String) -> Result<usize, String> {
    let q = open_ingest_queue(&project_root)?;
    q.cleanup().await.map_err(|e| e.to_string())
}

/// 修改任务优先级。
#[tauri::command]
pub async fn ingest_set_priority(
    project_root: String,
    task_id: String,
    priority: i32,
) -> Result<(), String> {
    let q = open_ingest_queue(&project_root)?;
    q.set_priority(&task_id, priority)
        .await
        .map_err(|e| e.to_string())
}

/// 删除已结束的任务记录（done / cancelled / failed）。
#[tauri::command]
pub async fn ingest_delete_task(project_root: String, task_id: String) -> Result<bool, String> {
    let q = open_ingest_queue(&project_root)?;
    q.delete_task(&task_id).await.map_err(|e| e.to_string())
}

/// 把任务标记为完成（由后台 worker 在 PDF 处理成功后调用）。
#[tauri::command]
pub async fn ingest_mark_done(project_root: String, task_id: String) -> Result<(), String> {
    let q = open_ingest_queue(&project_root)?;
    q.mark_done(&task_id).await.map_err(|e| e.to_string())
}

/// 把任务标记为失败（带错误信息），由后台 worker 调用。
#[tauri::command]
pub async fn ingest_mark_failed(
    project_root: String,
    task_id: String,
    error: String,
) -> Result<(), String> {
    let q = open_ingest_queue(&project_root)?;
    q.mark_failed(&task_id, error)
        .await
        .map_err(|e| e.to_string())
}

/// 拉取下一个 pending 任务（worker 启动时调用）。
#[tauri::command]
pub async fn ingest_dequeue(project_root: String) -> Result<Option<IngestTask>, String> {
    let q = open_ingest_queue(&project_root)?;
    q.dequeue().await.map_err(|e| e.to_string())
}


