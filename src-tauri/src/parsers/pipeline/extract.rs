use crate::parsers::doc_types::{ImageRef, OcrBlock};
use crate::parsers::chem::vlm_chem::{process_page_image, DetectedMolecule};
use std::path::{Path, PathBuf};

/// 分类并提取文件（自动检测 parser）
#[derive(Debug, Clone, serde::Serialize)]
pub struct ClassifyResult {
    pub text: String,
    pub page_count: usize,
    pub parser: String,
    pub images: Vec<ImageRef>,
    pub ocr_blocks: Vec<OcrBlock>,
}

/// 将提取的图片持久化到项目 reports/figures/<doc>/ 下
fn persist_extracted_images(
    path: &str,
    extracted: &[crate::parsers::pdf::images::ExtractedImage],
) -> Vec<ImageRef> {
    let source_path = Path::new(path);
    let project_root = find_project_root(source_path, None);
    let doc_slug = source_path
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("unknown")
        .to_string();

    let media_dir = project_root.as_ref().map(|root| {
        root.join(crate::core::constants::REPORTS_DIR)
            .join("figures")
            .join(&doc_slug)
    });

    extracted
        .iter()
        .map(|img| {
            let rel_path = if let Some(ref dir) = media_dir {
                if std::fs::create_dir_all(dir).is_ok() {
                    let dest = dir.join(&img.filename);
                    if let Err(e) = std::fs::copy(&img.path, &dest) {
                        log::warn!(
                            "Failed to copy image {} to {}: {}",
                            img.path.display(),
                            dest.display(),
                            e
                        );
                    } else {
                        // 计算相对项目根目录的路径
                        if let Some(ref root) = project_root {
                            if let Ok(rp) = dest.strip_prefix(root) {
                                return ImageRef {
                                    filename: img.filename.clone(),
                                    page: img.page,
                                    region: None,
                                    description: None,
                                    esmiles: None,
                                    rel_path: Some(rp.to_string_lossy().to_string()),
                                };
                            }
                        }
                    }
                }
                None
            } else {
                None
            };
            ImageRef {
                filename: img.filename.clone(),
                page: img.page,
                region: None,
                description: None,
                esmiles: None,
                rel_path,
            }
        })
        .collect()
}

// ---------------------------------------------------------------------------
// OCR 缓存
// ---------------------------------------------------------------------------

/// 返回项目 OCR 缓存目录
fn ocr_cache_dir(project_root: &Path) -> PathBuf {
    project_root
        .join(crate::core::constants::INDEX_DIR)
        .join("ocr-cache")
}

/// 计算 PDF 文件的缓存键（基于文件内容 SHA-256）
fn ocr_cache_key(path: &str) -> Option<String> {
    crate::core::helpers::sha256_file(Path::new(path)).ok()
}

/// 从缓存读取 OCR 结果（含图片引用 + OCR 块）
fn get_cached_ocr(path: &str, project_root: &Path) -> Option<(String, Vec<ImageRef>, Vec<OcrBlock>)> {
    let hash = ocr_cache_key(path)?;
    let cache_file = ocr_cache_dir(project_root).join(format!("{}.json", hash));
    let content = std::fs::read_to_string(&cache_file).ok()?;
    let val: serde_json::Value = serde_json::from_str(&content).ok()?;
    let text = val["text"].as_str()?.to_string();
    let images: Vec<ImageRef> = val["images"]
        .as_array()
        .map(|arr| {
            arr.iter()
                .filter_map(|v| serde_json::from_value(v.clone()).ok())
                .collect()
        })
        .unwrap_or_default();
    let ocr_blocks: Vec<OcrBlock> = val["ocr_blocks"]
        .as_array()
        .map(|arr| {
            arr.iter()
                .filter_map(|v| serde_json::from_value(v.clone()).ok())
                .collect()
        })
        .unwrap_or_default();
    Some((text, images, ocr_blocks))
}

/// 将 OCR 结果写入缓存（含图片引用 + OCR 块）
fn save_ocr_cache(path: &str, project_root: &Path, text: &str, images: &[ImageRef], ocr_blocks: &[OcrBlock]) {
    if let Some(hash) = ocr_cache_key(path) {
        let dir = ocr_cache_dir(project_root);
        if std::fs::create_dir_all(&dir).is_ok() {
            let cache_file = dir.join(format!("{}.json", hash));
            let val = serde_json::json!({
                "text": text,
                "images": images,
                "ocr_blocks": ocr_blocks,
                "timestamp": chrono::Utc::now().timestamp(),
            });
            if let Err(e) = std::fs::write(&cache_file, val.to_string()) {
                log::warn!("Failed to write OCR cache {}: {}", cache_file.display(), e);
            }
        }
    }
}

// ---------------------------------------------------------------------------
// MinerU 图片持久化
// ---------------------------------------------------------------------------

/// 将 MinerU zip 中提取的图片复制到项目 media 目录，并更新 rel_path。
fn persist_mineru_images(
    path: &str,
    project_root: &Path,
    mineru_images: &[ImageRef],
) -> Vec<ImageRef> {
    let source_path = Path::new(path);
    let doc_slug = source_path
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("unknown");

    let media_dir = project_root
        .join(crate::core::constants::REPORTS_DIR)
        .join("figures")
        .join(doc_slug)
        .join("mineru");

    if std::fs::create_dir_all(&media_dir).is_err() {
        log::warn!("Failed to create mineru-images dir: {}", media_dir.display());
        return mineru_images.to_vec();
    }

    mineru_images
        .iter()
        .map(|img| {
            let rel = img.rel_path.as_ref().unwrap_or(&img.filename);
            let src = Path::new(rel);
            if !src.exists() {
                // 如果临时文件已被清理，保留原样
                return img.clone();
            }
            let dest = media_dir.join(&img.filename);
            if let Err(e) = std::fs::copy(src, &dest) {
                log::warn!(
                    "Failed to copy MinerU image {} → {}: {}",
                    src.display(),
                    dest.display(),
                    e
                );
                return img.clone();
            }
            // 计算相对项目根目录的路径
            if let Ok(rp) = dest.strip_prefix(project_root) {
                ImageRef {
                    filename: img.filename.clone(),
                    page: img.page,
                    region: img.region.clone(),
                    description: img.description.clone(),
                    esmiles: img.esmiles.clone(),
                    rel_path: Some(rp.to_string_lossy().to_string()),
                }
            } else {
                img.clone()
            }
        })
        .collect()
}

// ---------------------------------------------------------------------------
// classify_and_extract
// ---------------------------------------------------------------------------

pub async fn classify_and_extract(path: &str) -> Result<ClassifyResult, String> {
    let source_path = Path::new(path);
    let project_root = find_project_root(source_path, None);

    // 先尝试 pdf-inspector
    let pdf_result =
        pdf_inspector::process_pdf(path).map_err(|e| format!("pdf-inspector failed: {}", e))?;
    let md = pdf_result.markdown.unwrap_or_default();
    let page_count = pdf_result.page_count as usize;

    // 提取嵌入图片并持久化到项目目录
    let tmp_dir = tempfile::tempdir().map_err(|e| format!("Temp dir error: {}", e))?;
    let extracted = crate::parsers::pdf::images::extract_images_from_pdf(path, tmp_dir.path(), 50, 5)
        .unwrap_or_default();
    let images = persist_extracted_images(path, &extracted);

    // 判断是否为扫描件（文本极少但有页面）
    let is_scanned = md.len() < 100 && page_count > 0;

    if is_scanned {
        // 优先尝试 MinerU（云端 OCR）
        if std::env::var("MINERU_API_KEY").is_ok() {
            // 检查缓存
            if let Some(ref root) = project_root {
                if let Some((cached_text, cached_images, cached_blocks)) = get_cached_ocr(path, root) {
                    log::info!("OCR cache HIT for {}", path);
                    let mut all_images = images;
                    all_images.extend(cached_images);
                    return Ok(ClassifyResult {
                        text: cached_text,
                        page_count,
                        parser: "mineru+cache".into(),
                        images: all_images,
                        ocr_blocks: cached_blocks,
                    });
                }
            }

            let host =
                std::env::var("MINERU_HOST").unwrap_or_else(|_| "https://mineru.net".to_string());
            let api_key = std::env::var("MINERU_API_KEY").unwrap_or_default();
            let client = crate::parsers::pdf::mineru::MineruClient::new(&host, &api_key);

            // 扫描文档使用优化参数：启用 OCR + 自动语言推断 + VLM 模型
            let options = crate::parsers::pdf::mineru::scanned_pdf_options(path);
            log::info!(
                "[MinerU] Parsing scanned PDF with options: is_ocr={}, language={}, model={}",
                options.is_ocr, options.language, options.model_version
            );

            match client.parse_file_with_options(path, &options) {
                Ok(result) => {
                    // 将 MinerU 提取的图片持久化到项目目录
                    let mineru_images = if let Some(ref root) = project_root {
                        persist_mineru_images(path, root, &result.images)
                    } else {
                        result.images
                    };

                    // 保存缓存
                    if let Some(ref root) = project_root {
                        save_ocr_cache(path, root, &result.markdown, &mineru_images, &result.ocr_blocks);
                    }

                    let mut all_images = images;
                    all_images.extend(mineru_images);
                    return Ok(ClassifyResult {
                        text: result.markdown,
                        page_count: 0,
                        parser: "mineru".into(),
                        images: all_images,
                        ocr_blocks: result.ocr_blocks,
                    });
                }
                Err(e) => {
                    log::warn!("MinerU OCR failed for {}: {}", path, e);
                }
            }
        }
        // 回退到 LiteParse（本地 OCR）
        if let Ok(result) = crate::parsers::pdf::liteparse::parse_with_liteparse(path, true, None).await
        {
            if !result.text.trim().is_empty() {
                return Ok(ClassifyResult {
                    text: result.text,
                    page_count: result.pages.len(),
                    parser: "liteparse".into(),
                    images,
                    ocr_blocks: vec![],
                });
            }
        }
    }

    Ok(ClassifyResult {
        text: md,
        page_count,
        parser: "pdf_inspector".into(),
        images,
        ocr_blocks: vec![],
    })
}

// ---------------------------------------------------------------------------
// 分子图像提取
// ---------------------------------------------------------------------------

/// 从 PDF 中提取分子图像（MolDet + MolScribe）
///
/// 根据 PDF 类型选择不同策略：
/// - TextBased（如中国专利）：LiteParse 截图每页 → MolDet 检测 → 裁剪 → MolScribe
/// - Scanned（如美国专利）：使用 lopdf 提取的位图 → MolDet 检测 → 裁剪 → MolScribe
///
/// # Arguments
/// * `path` - PDF 文件路径
/// * `classified` - `classify_and_extract` 的结果（用于判断类型和获取已提取图片）
/// * `sidecar_url` - Python sidecar URL
/// * `project_root` - 项目根目录（用于保存裁剪图）
pub async fn extract_molecules_from_pdf(
    path: &str,
    classified: &ClassifyResult,
    sidecar_url: &str,
    project_root: &Path,
) -> Result<Vec<DetectedMolecule>, String> {
    let is_scanned = classified.parser == "mineru" || classified.parser == "mineru+cache";

    // 确定输出目录
    let source_path = Path::new(path);
    let doc_slug = source_path
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("unknown");
    let mol_dir = project_root
        .join(crate::core::constants::MOLECULES_DIR)
        .join(doc_slug);

    std::fs::create_dir_all(&mol_dir)
        .map_err(|e| format!("Failed to create molecule dir: {}", e))?;

    let mut all_results = Vec::new();

    if is_scanned {
        // Scanned: 使用 lopdf 提取的位图
        log::info!(
            "[extract_molecules] Scanned PDF: processing {} embedded images from {}",
            classified.images.len(),
            path
        );

        for (idx, img_ref) in classified.images.iter().enumerate() {
            let img_path = if let Some(ref rp) = img_ref.rel_path {
                project_root.join(rp)
            } else {
                continue;
            };

            if !img_path.exists() {
                log::warn!("[extract_molecules] Image not found: {}", img_path.display());
                continue;
            }

            let page_idx = img_ref.page as i32;
            let output_dir = mol_dir.clone();

            match process_page_image(
                img_path.to_str().unwrap_or(""),
                page_idx,
                sidecar_url,
                &output_dir,
            )
            .await
            {
                Ok(results) => {
                    all_results.extend(results);
                }
                Err(e) => {
                    log::warn!(
                        "[extract_molecules] Failed to process image {} (page {}): {}",
                        img_path.display(),
                        page_idx,
                        e
                    );
                }
            }
        }
    } else {
        // TextBased: LiteParse 截图每页
        log::info!(
            "[extract_molecules] TextBased PDF: screenshot {} pages from {}",
            classified.page_count,
            path
        );

        // 生成页码列表（1-indexed for LiteParse）
        let page_numbers: Vec<u32> = (1..=classified.page_count).map(|p| p as u32).collect();

        // 分批截图（避免内存溢出，每批 10 页）
        let batch_size = 10usize;
        for batch_start in (0..page_numbers.len()).step_by(batch_size) {
            let batch_end = (batch_start + batch_size).min(page_numbers.len());
            let batch_pages: Vec<u32> = page_numbers[batch_start..batch_end].to_vec();

            match crate::parsers::pdf::liteparse::screenshot_with_liteparse(path, Some(batch_pages))
                .await
            {
                Ok(screenshots) => {
                    for ss in screenshots {
                        let page_idx = ss.page_num as i32; // page_num is 1-indexed
                        let page_img_path = mol_dir.join(format!("page_{:04}_screenshot.png", page_idx));
                        if let Err(e) = std::fs::write(&page_img_path, &ss.image_bytes) {
                            log::warn!(
                                "[extract_molecules] Failed to save screenshot page {}: {}",
                                page_idx,
                                e
                            );
                            continue;
                        }

                        let output_dir = mol_dir.clone();
                        match process_page_image(
                            page_img_path.to_str().unwrap_or(""),
                            page_idx,
                            sidecar_url,
                            &output_dir,
                        )
                        .await
                        {
                            Ok(results) => {
                                all_results.extend(results);
                            }
                            Err(e) => {
                                log::warn!(
                                    "[extract_molecules] Failed to process screenshot page {}: {}",
                                    page_idx,
                                    e
                                );
                            }
                        }
                    }
                }
                Err(e) => {
                    log::warn!(
                        "[extract_molecules] LiteParse screenshot failed for batch {}-{}: {}",
                        batch_start + 1,
                        batch_end,
                        e
                    );
                }
            }
        }
    }

    log::info!(
        "[extract_molecules] Total detected molecules from {}: {}",
        path,
        all_results.len()
    );

    Ok(all_results)
}

// ---------------------------------------------------------------------------
// 查找项目根目录（用于持久化）
// ---------------------------------------------------------------------------

pub fn find_project_root(
    start: &std::path::Path,
    explicit: Option<&str>,
) -> Option<std::path::PathBuf> {
    if let Some(root) = explicit {
        let p = std::path::PathBuf::from(root);
        if p.join(".mbforge").is_dir() {
            return Some(p);
        }
    }
    let mut current = start.parent()?;
    for _ in 0..5 {
        if current.join(".mbforge").is_dir() {
            return Some(current.to_path_buf());
        }
        current = current.parent()?;
    }
    None
}

// ---------------------------------------------------------------------------
// PDF 分子提取工作流（完整封装）
// ---------------------------------------------------------------------------

/// 工作流输出结果（复用已有类型）
#[derive(Debug, Clone, serde::Serialize)]
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
    pub molecules: Vec<crate::parsers::chem::vlm_chem::DetectedMolecule>,
}

/// 单个分子的元数据（写入 manifest.json）
#[derive(Debug, Clone, serde::Serialize)]
struct MoleculeEntry {
    index: usize,
    smiles: String,
    esmiles: Option<String>,
    name: String,
    page: i32,
    moldet_confidence: f64,
    molscribe_confidence: f64,
    image_file: String,
}

/// manifest.json 结构
#[derive(Debug, Clone, serde::Serialize)]
struct Manifest {
    source: String,
    parser: String,
    page_count: usize,
    text_file: String,
    molecules: Vec<MoleculeEntry>,
}

/// 完整的 PDF 分子提取工作流。
///
/// 输入 PDF → 提取文本 + 检测分子图片 + 识别 SMILES → 输出到指定目录。
///
/// # 输出结构
/// ```text
/// <output_dir>/
///   <pdf_name>/
///     text.md
///     molecules/
///       manifest.json
///       page_0001_mol_000.png
///       page_0001_mol_001.png
///       ...
/// ```
pub async fn extract_pdf_workflow(
    pdf_path: &str,
    output_dir: &str,
    sidecar_url: &str,
) -> Result<WorkflowResult, String> {
    use crate::parsers::chem::chem_validate::separate_esmiles_layers;

    let pdf = std::path::Path::new(pdf_path);
    if !pdf.exists() {
        return Err(format!("PDF not found: {}", pdf_path));
    }

    let pdf_name = pdf
        .file_stem()
        .map(|n| n.to_string_lossy().to_string())
        .unwrap_or_else(|| "output".to_string());

    // 创建输出目录结构
    let base_dir = std::path::Path::new(output_dir).join(&pdf_name);
    let mol_dir = base_dir.join("molecules");
    std::fs::create_dir_all(&mol_dir)
        .map_err(|e| format!("Failed to create output dir: {}", e))?;

    log::info!(
        "[workflow] Starting extraction: {} → {}",
        pdf_path,
        base_dir.display()
    );

    // Stage 1: 文本提取 + 分类
    let classified = classify_and_extract(pdf_path).await?;

    // 写入 text.md
    let text_path = base_dir.join("text.md");
    std::fs::write(&text_path, &classified.text)
        .map_err(|e| format!("Failed to write text.md: {}", e))?;

    log::info!(
        "[workflow] Text extracted: {} pages, {} chars, parser={}",
        classified.page_count,
        classified.text.len(),
        classified.parser
    );

    // Stage 2: 分子图像检测 + 识别
    let detected = extract_molecules_from_pdf(
        pdf_path,
        &classified,
        sidecar_url,
        &base_dir, // crop 图片保存到 molecules/ 下
    )
    .await
    .unwrap_or_else(|e| {
        log::warn!("[workflow] Molecule extraction failed: {}", e);
        vec![]
    });

    log::info!(
        "[workflow] Detected {} molecules",
        detected.len()
    );

    // Stage 3: 生成 manifest.json
    let molecules: Vec<MoleculeEntry> = detected
        .iter()
        .enumerate()
        .map(|(i, mol)| {
            // 裁剪图片文件名格式: page_XXXX_mol_YYY.png
            let image_file = format!("page_{:04}_mol_{:03}.png", mol.page, i);
            let (smiles, esmiles_opt, _tags) = separate_esmiles_layers(&mol.esmiles);
            MoleculeEntry {
                index: i,
                smiles,
                esmiles: esmiles_opt,
                name: format!("IMG-{}-P{}", pdf_name, mol.page),
                page: mol.page,
                moldet_confidence: mol.moldet_conf,
                molscribe_confidence: mol.confidence,
                image_file,
            }
        })
        .collect();

    let manifest = Manifest {
        source: pdf_name.clone(),
        parser: classified.parser.clone(),
        page_count: classified.page_count,
        text_file: "text.md".to_string(),
        molecules,
    };

    let manifest_path = mol_dir.join("manifest.json");
    let manifest_json = serde_json::to_string_pretty(&manifest)
        .map_err(|e| format!("Failed to serialize manifest: {}", e))?;
    std::fs::write(&manifest_path, manifest_json)
        .map_err(|e| format!("Failed to write manifest.json: {}", e))?;

    let result = WorkflowResult {
        output_dir: base_dir.to_string_lossy().to_string(),
        text_path: text_path.to_string_lossy().to_string(),
        manifest_path: manifest_path.to_string_lossy().to_string(),
        classify: classified,
        molecules: detected,
    };

    log::info!(
        "[workflow] Done: {} pages, {} molecules → {}",
        result.classify.page_count,
        result.molecules.len(),
        result.output_dir
    );

    Ok(result)
}
