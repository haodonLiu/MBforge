// PDF inspection commands — Task 2: classify_pdf

use serde::Serialize;
use crate::parsers::doc_types::OcrBlock;

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
    use crate::parsers::chem::vlm_chem::DetectedMolecule;

    let sidecar_url = crate::core::constants::sidecar_url();
    let result = crate::parsers::pipeline::extract_pdf_workflow(&path, &output_dir, &sidecar_url).await?;

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
            crate::parsers::pipeline::find_project_root(
                std::path::Path::new(&output_dir),
                None,
            )
        });

        if let Some(root) = project_root {
            if let Ok(db) = MoleculeDatabase::open(&root) {
                // 文本行缓存：同一页只解析一次 PDF
                let mut lines_cache: std::collections::HashMap<i32, Vec<crate::parsers::chem::label_assoc::TextLine>> =
                    std::collections::HashMap::new();
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
                                log::warn!("[extract_workflow] page {} text extraction failed: {}", page_num, e);
                                Vec::new()
                            }
                        }
                    });
                    let label_match = if mol.bbox_pdf != [0.0, 0.0, 0.0, 0.0] {
                        crate::parsers::chem::label_assoc::find_label_for_bbox(
                            (mol.bbox_pdf[0], mol.bbox_pdf[1], mol.bbox_pdf[2], mol.bbox_pdf[3]),
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
                        properties["context_text"] = serde_json::Value::String(m.context_text.clone());
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
                        log::warn!("[extract_workflow] Failed to add molecule {}: {}", mol_id, e);
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
                log::info!("[extract_workflow] Persisted {}/{} molecules to DB", saved, result.molecules.len());
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
    let mut update_status = |status: &str| {
        if let (Some(root), Some(id)) = (&project_root, &doc_id) {
            if let Some(mut project) = crate::core::project::Project::open(root) {
                project.set_document_ocr(id, status, &file_hash);
            }
        }
    };

    // 1. 尝试从缓存读取
    if let Some(ref root) = project_root {
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
                    let parser = val["parser"]
                        .as_str()
                        .unwrap_or("unknown")
                        .to_string();
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

    let result = crate::parsers::pipeline::classify_and_extract(&path).await;

    match result {
        Ok(classified) => {
            let has_blocks = !classified.ocr_blocks.is_empty();
            update_status(if has_blocks { "completed" } else { "not_processed" });
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
    let items = pdf_inspector::extractor::extract_text_with_positions_pages(
        pdf_path,
        Some(&first_page),
    )
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
