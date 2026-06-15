#![allow(dead_code)]
// PDF inspection commands — Task 2: classify_pdf

use crate::parsers::doc_types::OcrBlock;
use serde::Serialize;

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
/// Uses `pdf_inspector::detect_pdf` (ProcessMode::DetectOnly) for fast
/// classification (~10–50ms).  The returned `PdfClassification` contains
/// the PDF type, per-page OCR needs, and layout / encoding diagnostics
/// that the frontend can surface to the user.
#[tauri::command]
pub fn classify_pdf(path: String) -> Result<PdfClassification, String> {
    let result = pdf_inspector::detect_pdf(&path).map_err(|e| {
        log::error!("classify_pdf failed for path={}: {}", path, e);
        format!("pdf-inspector detect failed: {}", e)
    })?;

    let pdf_type = match result.pdf_type {
        pdf_inspector::PdfType::TextBased => "TextBased",
        pdf_inspector::PdfType::Scanned => "Scanned",
        pdf_inspector::PdfType::Mixed => "Mixed",
        pdf_inspector::PdfType::ImageBased => "ImageBased",
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
/// 2. 调用 `pdf_inspector::detect_pdf` 判定类型；
/// 3. 将结果写入 `projects/<doc_id>/cache/inspector.json`；
/// 4. 更新 DocumentProject / Project index 的 `inspector_status` 与 `ocr_status`。
#[tauri::command]
pub fn inspect_pdf(project_root: String, doc_id: String) -> Result<PdfClassification, String> {
    use crate::core::helpers::{clean_path, save_json};
    use crate::core::project::document_project::DocumentProject;
    use crate::core::project::project::Project;

    let root = std::path::PathBuf::from(clean_path(&project_root));

    let project =
        Project::open(&root).ok_or_else(|| format!("Cannot open project at {}", project_root))?;
    let source_path = project
        .get_document_source_path(&doc_id)
        .ok_or_else(|| format!("Document {} source path not found", doc_id))?;

    let result =
        pdf_inspector::detect_pdf(source_path.to_string_lossy().as_ref()).map_err(|e| {
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
        pdf_inspector::PdfType::TextBased => "TextBased",
        pdf_inspector::PdfType::Scanned => "Scanned",
        pdf_inspector::PdfType::Mixed => "Mixed",
        pdf_inspector::PdfType::ImageBased => "ImageBased",
    };

    // Persist inspector result to the DocumentProject cache.
    let inspector_json = serde_json::json!({
        "pdf_type": pdf_type_str,
        "confidence": result.confidence,
        "page_count": result.page_count,
        "pages_needing_ocr": result.pages_needing_ocr,
        "has_complex_layout": result.layout.is_complex,
        "has_encoding_issues": result.has_encoding_issues,
        "title": result.title,
        "inspected_at": chrono::Utc::now().to_rfc3339(),
    });
    if let Some(mut dp) = DocumentProject::load(&root, &doc_id) {
        let paths = dp.paths();
        let _ = std::fs::create_dir_all(&paths.cache_dir);
        let inspector_path = paths.cache_dir.join("inspector.json");
        let _ = save_json(&inspector_path, &inspector_json);

        // Update DocumentProject statuses.
        dp.set_inspector_status(pdf_type_str.to_lowercase().as_str());
        match result.pdf_type {
            pdf_inspector::PdfType::TextBased => {
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
            pdf_inspector::PdfType::TextBased => "not_needed",
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
) -> Result<serde_json::Value, String> {
    use crate::core::helpers::clean_path;
    use crate::core::project::document_project::DocumentProject;
    use crate::core::project::project::Project;

    let root = std::path::PathBuf::from(clean_path(&project_root));

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
        let q = crate::core::document::ingest_queue::IngestQueue::new(&root)
            .map_err(|e| format!("Failed to open ingest queue: {}", e))?;
        q.enqueue_with_stage(
            source_path.to_string_lossy().to_string(),
            doc_id.clone(),
            "ocr",
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

    Ok(serde_json::json!({
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
/// Uses `pdf_inspector::process_pdf` (ProcessMode::Full) for complete
/// extraction including text, tables, and layout detection.
#[tauri::command]
pub fn extract_text(path: String) -> Result<PdfExtraction, String> {
    let result = pdf_inspector::process_pdf(&path).map_err(|e| {
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

/// Tauri 命令：完整的 PDF 分子提取工作流。
///
/// 输入 PDF → 提取文本 + 检测分子图片 + 识别 SMILES → 输出到指定目录 + 写入 SQLite。
///
/// 输出结构（写入项目根目录下的规范位置，不再使用 `output_dir`）：
/// ```text
/// <project_root>/
///   reports/
///     <pdf_name>/text.md
///     figures/<pdf_name>/...
///   molecules/
///     <pdf_name>/manifest.json
///     <pdf_name>/page_*_mol_*.png
/// ```
///
/// `output_dir` 仍作为入参保留（向后兼容），但只有当它能解析为
/// 项目根目录时才会被使用；否则我们从 `path` 推导项目根。
#[tauri::command]
pub async fn extract_pdf_workflow_cmd(
    path: String,
    output_dir: String,
) -> Result<crate::parsers::pipeline::WorkflowResult, String> {
    use crate::core::molecule::molecule_store::{MoleculeDatabase, MoleculeImage, MoleculeRecord};
    use crate::parsers::chem::chem_validate::separate_esmiles_layers;

    let sidecar_url = crate::core::constants::sidecar_url();
    let result =
        crate::parsers::pipeline::extract_pdf_workflow(&path, &output_dir, &sidecar_url).await?;

    // 将检测到的分子写入 SQLite（molecules + molecule_images）
    let filename = std::path::Path::new(&path)
        .file_name()
        .map(|n| n.to_string_lossy().to_string())
        .unwrap_or_else(|| "unknown.pdf".to_string());

    if !result.molecules.is_empty() {
        // 优先从 path 推导项目根（canonical），output_dir 作为兜底
        let project_root = crate::parsers::pipeline::find_project_root(
            std::path::Path::new(&path),
            None,
        )
        .or_else(|| {
            crate::parsers::pipeline::find_project_root(std::path::Path::new(&output_dir), None)
        });

        if let Some(root) = project_root {
            if let Ok(db) = MoleculeDatabase::open(&root) {
                // 文本行缓存：同一页只解析一次 PDF
                let mut lines_cache: std::collections::HashMap<
                    i32,
                    Vec<crate::parsers::chem::label_assoc::TextLine>,
                > = std::collections::HashMap::new();
                let page_h_pts = get_page_height(&path).unwrap_or(842.0);

                let mut saved = 0usize;
                for (idx, mol) in result.molecules.iter().enumerate() {
                    let (clean_smiles, esmiles_opt, semantic_tags) =
                        separate_esmiles_layers(&mol.esmiles);

                    // ---- label 关联（在 bbox 上方找 "化合物 26A" / "实施例 5" 等）----
                    let page_num = (mol.page as i32).max(0);
                    let lines = lines_cache.entry(page_num).or_insert_with(|| {
                        match crate::parsers::chem::label_assoc::extract_page_text_lines(
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
                        crate::parsers::chem::label_assoc::find_label_for_bbox(
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
                        None => format!("IMG-{}-P{:03}-{:03}", filename, mol.page, idx),
                    };
                    let mut properties = serde_json::json!({});
                    if let Some(m) = &label_match {
                        properties["context_text"] =
                            serde_json::Value::String(m.context_text.clone());
                    }
                    properties["bbox_pdf"] = serde_json::json!(mol.bbox_pdf);

                    let mol_id = crate::core::helpers::generate_uuid();
                    let record = MoleculeRecord {
                        mol_id: mol_id.clone(),
                        smiles: clean_smiles,
                        esmiles: esmiles_opt,
                        semantic_tags,
                        name: resolved_name,
                        source_doc: filename.clone(),
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
                            image_id: crate::core::helpers::generate_uuid(),
                            mol_id: mol_id.clone(),
                            image_path: mol.crop_path.clone(),
                            page: Some(mol.page as usize),
                            vlm_esmiles: Some(mol.esmiles.clone()),
                            vlm_confidence: mol.confidence,
                            is_structure_diagram: true,
                            created_at: None,
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
                    result.molecules.len()
                );
            }
        }
    }

    // 注：[方案 1] PipelineOutput::from_filesystem 在 Rust 内部调用者
    // 用了，但 Tauri command 保持 WorkflowResult 返回以兼容前端。
    let _pipeline = crate::parsers::pipeline::PipelineOutput::from_filesystem(
        std::path::PathBuf::from(&result.text_path),
        std::path::PathBuf::from(&result.manifest_path),
        result.molecules.len(),
    );
    Ok(result)
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
    pub blocks: Vec<OcrBlock>,
    /// 是否来自缓存
    pub from_cache: bool,
}

/// Tauri 命令：获取文档的 OCR 布局数据（用于可视化）。
///
/// 优先从 OCR 缓存读取；如果没有缓存且文档需要 MinerU 解析，
/// 则调用 classify_and_extract 获取（不写入缓存）。
/// 若提供 doc_id，会在处理前后更新项目 index 中的 ocr_status。
#[tauri::command]
pub async fn get_document_ocr_layout(
    path: String,
    doc_id: Option<String>,
) -> Result<OcrLayoutResult, String> {
    let source_path = std::path::Path::new(&path);
    let project_root = crate::parsers::pipeline::find_project_root(source_path, None);
    let file_hash = crate::core::helpers::sha256_file(source_path).unwrap_or_default();

    // 辅助：更新 OCR 状态
    let update_status = |status: &str| {
        if let (Some(root), Some(id)) = (&project_root, &doc_id) {
            if let Some(mut project) = crate::core::project::Project::open(root) {
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
            let new_cache = root
                .join(crate::core::config::constants::PROJECTS_DIR)
                .join(id)
                .join("cache")
                .join("ocr")
                .join("ocr.json");
            if new_cache.exists() {
                if let Ok(content) = std::fs::read_to_string(&new_cache) {
                    if let Ok(val) = serde_json::from_str::<serde_json::Value>(&content) {
                        let text = val["text"].as_str().unwrap_or("").to_string();
                        let page_count = val["page_count"]
                            .as_u64()
                            .map(|n| n as usize)
                            .unwrap_or_else(|| text.lines().count().max(1));
                        let blocks: Vec<OcrBlock> = val["ocr_blocks"]
                            .as_array()
                            .map(|arr| {
                                arr.iter()
                                    .filter_map(|v| serde_json::from_value(v.clone()).ok())
                                    .collect()
                            })
                            .unwrap_or_default();
                        let parser = val["parser"].as_str().unwrap_or("unknown").to_string();
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
                }
            }
        }

        // 1b. 旧版按 hash 的缓存
        let cache_dir = root
            .join(crate::core::constants::PROJECT_META_DIR)
            .join("ocr-cache");
        let cache_file = cache_dir.join(format!("{}.json", file_hash));
        if cache_file.exists() {
            if let Ok(content) = std::fs::read_to_string(&cache_file) {
                if let Ok(val) = serde_json::from_str::<serde_json::Value>(&content) {
                    let text = val["text"].as_str().unwrap_or("").to_string();
                    let page_count = text.lines().count().max(1);
                    let blocks: Vec<OcrBlock> = val["ocr_blocks"]
                        .as_array()
                        .map(|arr| {
                            arr.iter()
                                .filter_map(|v| serde_json::from_value(v.clone()).ok())
                                .collect()
                        })
                        .unwrap_or_default();
                    let parser = val["parser"].as_str().unwrap_or("unknown").to_string();
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
            }
        }
    }

    // 2. 缓存未命中：调用 classify_and_extract 获取
    log::info!("OCR layout cache MISS for {}, running extraction...", path);
    update_status("processing");

    let result = crate::parsers::pipeline::classify_and_extract(&path, true).await;

    match result {
        Ok(classified) => {
            let has_blocks = !classified.ocr_blocks.is_empty();
            update_status(if has_blocks {
                "completed"
            } else {
                "not_processed"
            });
            Ok(OcrLayoutResult {
                path: path.clone(),
                parser: classified.parser,
                page_count: classified.page_count,
                blocks: classified.ocr_blocks,
                from_cache: false,
            })
        }
        Err(e) => {
            update_status("error");
            Err(e)
        }
    }
}

/// 从 PDF 第一页拿页面高度（点单位）。仅用于 label 关联时的坐标转换。
/// 拿不到时返回 842.0（A4 高度）。
fn get_page_height(pdf_path: &str) -> Option<f64> {
    use std::collections::HashSet;
    let mut first_page: HashSet<u32> = HashSet::new();
    first_page.insert(1);
    let items =
        pdf_inspector::extractor::extract_text_with_positions_pages(pdf_path, Some(&first_page))
            .ok()?;
    // 用首个 item 的 height 字段反推页面尺寸不行；
    // 直接走 pdf_inspector 的 page_height API
    let _ = items;
    // 走 Document API 拿页面尺寸
    let doc = lopdf::Document::load(pdf_path).ok()?;
    let pages = doc.get_pages();
    let first_id = *pages.values().next()?;
    let page_dict = doc.get_dictionary(first_id).ok()?;
    let media_box = page_dict.get(b"MediaBox").ok()?;
    let arr = media_box.as_array().ok()?;
    if arr.len() < 4 {
        return None;
    }
    let h = match &arr[3] {
        lopdf::Object::Real(r) => *r as f64,
        lopdf::Object::Integer(i) => *i as f64,
        _ => return None,
    };
    Some(h)
}

/// 把识别出的图像插入到 markdown：内联引用 + 末尾"## Extracted Images"。
/// pipeline 内部不再调用，留给前端需要"图 + 文字"合成展示时按需触发。
#[tauri::command]
pub fn augment_markdown_with_images(
    markdown: String,
    images: Vec<crate::parsers::doc_types::ImageRef>,
    ocr_blocks: Option<Vec<crate::parsers::doc_types::OcrBlock>>,
) -> String {
    crate::parsers::pipeline::markdown_augment::augment_markdown_with_images(
        &markdown,
        &images,
        ocr_blocks.as_deref(),
    )
}

// ─── IngestQueue：PDF 异步处理队列 ────────────────────────────────

use crate::core::document::ingest_queue::{IngestQueue, IngestStatus, IngestTask, QueueStats};

fn open_ingest_queue(project_root: &str) -> Result<IngestQueue, String> {
    IngestQueue::new(std::path::Path::new(project_root))
        .map_err(|e: crate::core::error::AppError| e.to_string())
}

/// 入队一个 PDF 供异步处理。返回任务 ID。
#[tauri::command]
pub async fn ingest_enqueue(
    project_root: String,
    file_path: String,
    doc_id: String,
) -> Result<String, String> {
    let q = open_ingest_queue(&project_root)?;
    q.enqueue(file_path, doc_id)
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

// re-export for handler!()
#[allow(unused_imports)]
use IngestStatus as _IngestStatusReexport;
