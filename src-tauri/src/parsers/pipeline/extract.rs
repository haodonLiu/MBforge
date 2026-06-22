#![allow(dead_code)]
use crate::core::config::constants::{
    MOLECULES_DIR, PROJECTS_DIR, PROJECT_SOURCE_FILE, REPORTS_DIR,
};
use crate::core::document::detection_cache::{
    Detection as CachedDetection, DetectionCache, PageDetection, DETECTION_CACHE_SCHEMA_VERSION,
};
use crate::parsers::chem::vlm_chem::{
    coref_to_molecules, detect_batch as detect_batch_images, detect_coref, molscribe,
    process_page_image, CorefMolecule, DetectedMolecule,
};
use crate::parsers::doc_types::{ImageRef, OcrBlock};
use crate::parsers::pdf::context::PdfInspectorContext;
use crate::parsers::pdf::images::{
    image_to_pdf_bbox, pdf_page_size_pts, pdf_to_image_bbox, scale_from_page_size,
};
use image::GenericImageView;
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

/// 可选的进度/日志回调，用于把 `classify_and_extract` 内部的子步骤反馈给前端。
pub trait ExtractProgressReporter: Send + Sync {
    /// 报告一条人类可读的子步骤消息。
    fn report(&self, message: &str);
}

/// 将提取的图片持久化到项目 reports/figures/<doc>/ 下
pub fn persist_extracted_images(
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

    let media_dir = project_root
        .as_ref()
        .map(|root| root.join(REPORTS_DIR).join("figures").join(&doc_slug));

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

/// 计算 PDF 文件的缓存键（基于文件内容 SHA-256 + 目标页列表）
fn ocr_cache_key(path: &str, pages: &[usize]) -> Option<String> {
    let base = crate::core::helpers::sha256_file(Path::new(path)).ok()?;
    if pages.is_empty() {
        return Some(base);
    }
    use sha2::Digest;
    let mut hasher = sha2::Sha256::new();
    hasher.update(base.as_bytes());
    for p in pages {
        hasher.update(p.to_le_bytes());
    }
    Some(format!("{:x}", hasher.finalize()))
}

/// 从缓存读取 OCR 结果（含图片引用 + OCR 块）
fn get_cached_ocr(
    path: &str,
    project_root: &Path,
    pages: &[usize],
) -> Option<(String, Vec<ImageRef>, Vec<OcrBlock>)> {
    let hash = ocr_cache_key(path, pages)?;
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
fn save_ocr_cache(
    path: &str,
    project_root: &Path,
    text: &str,
    images: &[ImageRef],
    ocr_blocks: &[OcrBlock],
    pages: &[usize],
) {
    if let Some(hash) = ocr_cache_key(path, pages) {
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

/// Merge OCR output for selected pages with pdf-inspector markdown for the rest.
///
/// If the markdown does not contain page markers, falls back to the OCR text
/// when any pages needed OCR.
fn merge_ocr_with_markdown(markdown: &str, ocr_text: &str, pages: &[usize]) -> String {
    if pages.is_empty() {
        return ocr_text.to_string();
    }

    let page_markers: Vec<(usize, usize)> = markdown
        .match_indices("<!-- Page ")
        .filter_map(|(idx, _)| {
            let rest = &markdown[idx + 9..];
            rest.split_once(" -->")
                .and_then(|(num, _)| num.parse::<usize>().ok())
                .map(|n| (idx, n))
        })
        .collect();

    if page_markers.is_empty() {
        return ocr_text.to_string();
    }

    let page_set: std::collections::HashSet<usize> = pages.iter().copied().collect();
    let mut result = String::new();
    let mut last_end = 0;

    for (i, (_start, page_num)) in page_markers.iter().enumerate() {
        let end = if i + 1 < page_markers.len() {
            page_markers[i + 1].0
        } else {
            markdown.len()
        };

        if page_set.contains(page_num) {
            if result.is_empty() {
                result.push_str(ocr_text);
            }
        } else {
            result.push_str(&markdown[last_end..end]);
        }
        last_end = end;
    }

    if result.is_empty() {
        ocr_text.to_string()
    } else {
        result
    }
}

// ---------------------------------------------------------------------------
// MinerU 图片持久化
// ---------------------------------------------------------------------------

/// 将 MinerU zip 中提取的图片复制到项目 media 目录，并更新 rel_path。
/// Copy images from a backend temp dir into
/// `<project_root>/reports/figures/<doc_slug>/<backend_subdir>/` and
/// return their `ImageRef` with `rel_path` updated. Used by MinerU and
/// PaddleOCR branches.
fn persist_backend_images(
    path: &str,
    project_root: &Path,
    images: &[ImageRef],
    backend_subdir: &str,
) -> Vec<ImageRef> {
    let source_path = Path::new(path);
    let doc_slug = source_path
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("unknown");

    let media_dir = project_root
        .join(REPORTS_DIR)
        .join("figures")
        .join(doc_slug)
        .join(backend_subdir);

    if std::fs::create_dir_all(&media_dir).is_err() {
        log::warn!(
            "Failed to create {}-images dir: {}",
            backend_subdir,
            media_dir.display()
        );
        return images.to_vec();
    }

    images
        .iter()
        .map(|img| {
            let rel = img.rel_path.as_ref().unwrap_or(&img.filename);
            let src = Path::new(rel);
            if !src.exists() {
                return img.clone();
            }
            let dest = media_dir.join(&img.filename);
            if let Err(e) = std::fs::copy(src, &dest) {
                log::warn!(
                    "Failed to copy {} image {} → {}: {}",
                    backend_subdir,
                    src.display(),
                    dest.display(),
                    e
                );
                return img.clone();
            }
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

/// Back-compat shim — MinerU branch keeps the original name.
fn persist_mineru_images(
    path: &str,
    project_root: &Path,
    images: &[ImageRef],
) -> Vec<ImageRef> {
    persist_backend_images(path, project_root, images, "mineru")
}

// ---------------------------------------------------------------------------
// classify_and_extract
// ---------------------------------------------------------------------------

pub async fn classify_and_extract(path: &str, allow_ocr: bool) -> Result<ClassifyResult, String> {
    classify_and_extract_with_progress(path, allow_ocr, None).await
}

pub async fn classify_and_extract_with_progress(
    path: &str,
    allow_ocr: bool,
    progress: Option<&dyn ExtractProgressReporter>,
) -> Result<ClassifyResult, String> {
    let ctx = PdfInspectorContext::from_path(path).await?;
    classify_and_extract_from_context_with_path(&ctx, path, allow_ocr, progress).await
}

pub async fn classify_and_extract_from_context_with_path(
    ctx: &PdfInspectorContext,
    path: &str,
    allow_ocr: bool,
    progress: Option<&dyn ExtractProgressReporter>,
) -> Result<ClassifyResult, String> {
    let source_path = Path::new(path);
    let project_root = find_project_root(source_path, None);

    let md = ctx.markdown.clone();
    let page_count = ctx.page_count;
    let pages_needing_ocr = ctx.pages_needing_ocr.clone();

    // 提取嵌入图片并持久化到项目目录 (sync + I/O → spawn_blocking)
    let path_owned = path.to_owned();
    let (extracted, _tmp) = tokio::task::spawn_blocking(
        move || -> Result<(Vec<crate::parsers::pdf::images::ExtractedImage>, tempfile::TempDir), String> {
            let tmp = tempfile::tempdir()
                .map_err(|e| format!("failed to create temp dir: {e}"))?;
            let images = crate::parsers::pdf::images::extract_images_from_pdf(
                &path_owned,
                tmp.path(),
                50,
                5,
            )
            .unwrap_or_default();
            Ok((images, tmp))
        },
    )
    .await
    .map_err(|e| format!("image extraction join error: {e}"))?
    .map_err(|e| format!("image extraction failed: {e}"))?;
    let images = persist_extracted_images(path, &extracted);

    // 判断是否为扫描件（文本极少但有页面，或 pdf-inspector 标记需 OCR）
    let is_scanned =
        (md.len() < 100 && page_count > 0) || !pages_needing_ocr.is_empty();

    if is_scanned && allow_ocr {
        if let Some(p) = progress.as_ref() {
            p.report("检测到扫描件，将调用 OCR backend");
        }

        // 检查缓存（页列表参与缓存键）
        if let Some(ref root) = project_root {
            if let Some((cached_text, cached_images, cached_blocks)) =
                get_cached_ocr(path, root, &pages_needing_ocr)
            {
                log::info!("OCR cache HIT for {}", path);
                if let Some(p) = progress.as_ref() {
                    p.report("OCR 缓存命中，跳过 backend 调用");
                }
                let mut all_images = images.clone();
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

        for backend in crate::parsers::ocr::backend::available_backends() {
            if !backend.is_available() {
                log::warn!("OCR backend '{}' unavailable", backend.name());
                continue;
            }

            log::info!("[{}] Parsing scanned PDF {}", backend.name(), path);
            if let Some(p) = progress.as_ref() {
                p.report(&format!("尝试 {} OCR backend...", backend.name()));
            }

            let pages = pages_needing_ocr.clone();
            match backend.run_pages(path, &pages).await {
                Ok(out) => {
                    if let Some(p) = progress.as_ref() {
                        p.report(&format!("{} OCR 成功", backend.name()));
                    }

                    // 将 backend 临时图片持久化到项目目录。
                    let backend_images = if let Some(ref root) = project_root {
                        persist_backend_images(path, root, &out.images, backend.name())
                    } else {
                        out.images
                    };

                    let mut all_images = images.clone();
                    all_images.extend(backend_images);

                    // 尝试将 OCR 页与 pdf-inspector markdown 合并。
                    let merged_text = merge_ocr_with_markdown(&md, &out.text, &pages);

                    // 缓存键包含页列表。
                    if let Some(ref root) = project_root {
                        save_ocr_cache(
                            path,
                            root,
                            &merged_text,
                            &all_images,
                            &out.ocr_blocks,
                            &pages,
                        );
                    }

                    return Ok(ClassifyResult {
                        text: merged_text,
                        page_count: out.page_count.max(page_count),
                        parser: backend.name().into(),
                        images: all_images,
                        ocr_blocks: out.ocr_blocks,
                    });
                }
                Err(e) => {
                    log::warn!("{} OCR failed for {}: {}", backend.name(), path, e);
                    if let Some(p) = progress.as_ref() {
                        p.report(&format!("{} OCR 失败: {}", backend.name(), e));
                    }
                }
            }
        }

        if let Some(p) = progress.as_ref() {
            p.report("无可用 OCR 后端，将回退到 pdf-inspector 原始文本");
        }
    }

    if is_scanned {
        if let Some(p) = progress.as_ref() {
            if allow_ocr {
                p.report("OCR 未成功，回退到 pdf-inspector 原始文本");
            } else {
                p.report("扫描件已识别，但当前任务不允许 OCR，将使用 pdf-inspector 文本");
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
// DocumentProject-aware path helpers
// ---------------------------------------------------------------------------

/// If `source_path` is a DocumentProject source file
/// (`projects/<doc_id>/source.pdf`), return the `<doc_id>`.
fn document_project_id_from_source_path(project_root: &Path, source_path: &Path) -> Option<String> {
    let projects_dir = project_root.join(PROJECTS_DIR);
    if !source_path.starts_with(&projects_dir) {
        return None;
    }
    if source_path.file_name()?.to_str()? != PROJECT_SOURCE_FILE {
        return None;
    }
    source_path
        .parent()?
        .file_name()?
        .to_str()
        .map(|s| s.to_string())
}

/// Return the molecule output directory for a PDF.
///
/// - DocumentProject: `projects/<doc_id>/molecules/`
/// - Legacy: `molecules/<doc_slug>/`
fn molecule_output_dir(project_root: &Path, source_path: &Path, doc_slug: &str) -> PathBuf {
    if let Some(doc_id) = document_project_id_from_source_path(project_root, source_path) {
        project_root
            .join(PROJECTS_DIR)
            .join(doc_id)
            .join(MOLECULES_DIR)
    } else {
        project_root.join(MOLECULES_DIR).join(doc_slug)
    }
}

/// Return the temporary working directory for a PDF (screenshots, etc.).
///
/// - DocumentProject: `projects/<doc_id>/cache/tmp/`
/// - Legacy: `molecules/<doc_slug>/`
fn tmp_output_dir(project_root: &Path, source_path: &Path, doc_slug: &str) -> PathBuf {
    if let Some(doc_id) = document_project_id_from_source_path(project_root, source_path) {
        project_root
            .join(PROJECTS_DIR)
            .join(doc_id)
            .join("cache")
            .join("tmp")
    } else {
        project_root.join(MOLECULES_DIR).join(doc_slug)
    }
}

/// Return the detection cache + cache key for a PDF.
///
/// - DocumentProject: `projects/<doc_id>/cache/detections/`, key = doc_id
/// - Legacy: `index/detections/<doc_slug>/`, key = doc_slug
fn detection_cache_for_pdf(
    project_root: &Path,
    source_path: &Path,
    fallback_slug: &str,
) -> (DetectionCache, String) {
    if let Some(doc_id) = document_project_id_from_source_path(project_root, source_path) {
        (
            DetectionCache::for_document_project(project_root, &doc_id),
            doc_id,
        )
    } else {
        (DetectionCache::new(project_root), fallback_slug.to_string())
    }
}

// ---------------------------------------------------------------------------
// 分子图像提取
// ---------------------------------------------------------------------------

/// Write a single page's detections to the persistent detection cache.
///
/// Best-effort: any I/O error is logged but does not fail the pipeline.
/// `doc_slug` is used as the cache directory name (matches the existing
/// `molecules/<doc_slug>/` convention) so the cache is stable across
/// sessions and survives doc_id UUID regeneration.
fn write_detection_cache(
    project_root: &Path,
    source_path: &Path,
    doc_slug: &str,
    page: usize,
    pdf_hash: &str,
    pdf_mtime: f64,
    detections: &[DetectedMolecule],
) {
    let (cache, cache_key) = detection_cache_for_pdf(project_root, source_path, doc_slug);
    let now = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs_f64())
        .unwrap_or(0.0);

    let cached: Vec<CachedDetection> = detections
        .iter()
        .map(|d| {
            // crop_path from VLM Chem may be absolute or project-relative;
            // normalize to project-root-relative.
            let crop_abs = std::path::Path::new(&d.crop_path);
            let crop_rel = crop_abs
                .strip_prefix(project_root)
                .map(|p| p.to_string_lossy().to_string())
                .unwrap_or_else(|_| d.crop_path.clone());
            CachedDetection {
                // BBox in PDF coords is not currently returned by vlm_chem
                // (only image-px coords). Use zeros as a placeholder until
                // the on-demand path also writes bboxes.
                bbox_pdf: [0.0, 0.0, 0.0, 0.0],
                // vlm_chem returns esmiles only; SMILES inference happens
                // downstream in chem_validate. Leave empty here.
                smiles: None,
                esmiles: Some(d.esmiles.clone()).filter(|s| !s.is_empty()),
                conf_moldet: d.moldet_conf,
                conf_molscribe: d.confidence,
                vlm_caption: None,
                vlm_esmiles: None,
                crop_relpath: Some(crop_rel).filter(|s| !s.is_empty()),
                is_quick_scan: false,
            }
        })
        .collect();

    let entry = PageDetection {
        doc_id: cache_key.clone(),
        page,
        pdf_hash: pdf_hash.to_string(),
        mtime: pdf_mtime,
        detected_at: now,
        schema_version: DETECTION_CACHE_SCHEMA_VERSION,
        detections: cached,
    };

    if let Err(e) = cache.put(&entry) {
        log::warn!(
            "[detection_cache] Failed to write cache for {} page {}: {}",
            cache_key,
            page,
            e
        );
    }
}

// ---------------------------------------------------------------------------
// 复用 quick-scan bbox 进行完整识别（Phase 5）
// ---------------------------------------------------------------------------

/// Convert a recognized molecule into a cache Detection entry.
fn detected_molecule_to_cached_detection(
    mol: &DetectedMolecule,
    project_root: &Path,
    is_quick_scan: bool,
) -> CachedDetection {
    let crop_abs = Path::new(&mol.crop_path);
    let crop_rel = crop_abs
        .strip_prefix(project_root)
        .map(|p| p.to_string_lossy().to_string())
        .unwrap_or_else(|_| mol.crop_path.clone());
    CachedDetection {
        bbox_pdf: mol.bbox_pdf,
        smiles: None,
        esmiles: Some(mol.esmiles.clone()).filter(|s| !s.is_empty()),
        conf_moldet: mol.moldet_conf,
        conf_molscribe: mol.confidence,
        vlm_caption: None,
        vlm_esmiles: None,
        crop_relpath: Some(crop_rel).filter(|s| !s.is_empty()),
        is_quick_scan,
    }
}

fn now_secs_f64() -> f64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs_f64())
        .unwrap_or(0.0)
}

fn bbox_close(a: &[f64; 4], b: &[f64; 4]) -> bool {
    a.iter().zip(b.iter()).all(|(x, y)| (x - y).abs() < 1.0)
}

/// Merge newly-recognized full detections into an existing quick-scan page
/// entry and persist it. Any quick-scan bboxes that were successfully
/// recognized are replaced by full entries; unrecognized quick-scan bboxes
/// are preserved so the user can still click them on-demand.
fn merge_and_write_full_detections(
    cache: &DetectionCache,
    cache_key: &str,
    page: usize,
    pdf_hash: &str,
    pdf_mtime: f64,
    existing: PageDetection,
    recognized: &[DetectedMolecule],
    project_root: &Path,
) {
    if recognized.is_empty() {
        return;
    }

    let mut detections: Vec<CachedDetection> = recognized
        .iter()
        .map(|m| detected_molecule_to_cached_detection(m, project_root, false))
        .collect();

    for d in existing.detections {
        if !d.is_quick_scan {
            continue;
        }
        if recognized
            .iter()
            .any(|m| bbox_close(&m.bbox_pdf, &d.bbox_pdf))
        {
            continue;
        }
        detections.push(d);
    }

    let entry = PageDetection {
        doc_id: cache_key.to_string(),
        page,
        pdf_hash: pdf_hash.to_string(),
        mtime: pdf_mtime,
        detected_at: now_secs_f64(),
        schema_version: DETECTION_CACHE_SCHEMA_VERSION,
        detections,
    };

    if let Err(e) = cache.put(&entry) {
        log::warn!(
            "[detection_cache] Failed to write merged cache for {} page {}: {}",
            cache_key,
            page,
            e
        );
    }
}

/// Run MolScribe on crops derived from cached quick-scan bboxes.
///
/// `page_size` is the PDF page size in points; when available the cached
/// PDF bbox is converted back to image pixels. If unavailable, the cached
/// bbox is assumed to already be in image coordinates (fallback path for
/// scanned PDFs where page size could not be determined).
async fn recognize_cached_page(
    image_path: &Path,
    page_idx: i32,
    page_size: Option<(f64, f64)>,
    sidecar_url: &str,
    output_dir: &Path,
    cached: &[CachedDetection],
) -> Result<Vec<DetectedMolecule>, String> {
    let img = image::open(image_path)
        .map_err(|e| format!("Failed to open image {}: {}", image_path.display(), e))?;
    let (img_w, img_h) = img.dimensions();
    std::fs::create_dir_all(output_dir)
        .map_err(|e| format!("Failed to create output dir: {}", e))?;

    let mut results = Vec::new();
    for (idx, d) in cached.iter().filter(|d| d.is_quick_scan).enumerate() {
        let (x1, y1, x2, y2) = match page_size {
            Some((pw, ph)) if pw > 0.0 && ph > 0.0 => {
                let scale = scale_from_page_size(pw, ph, img_w, img_h);
                pdf_to_image_bbox(
                    (d.bbox_pdf[0], d.bbox_pdf[1], d.bbox_pdf[2], d.bbox_pdf[3]),
                    ph,
                    scale,
                )
            }
            _ => (d.bbox_pdf[0], d.bbox_pdf[1], d.bbox_pdf[2], d.bbox_pdf[3]),
        };

        let x1 = x1.max(0.0) as u32;
        let y1 = y1.max(0.0) as u32;
        let x2 = x2.min(img_w as f64) as u32;
        let y2 = y2.min(img_h as f64) as u32;
        if x2 <= x1 || y2 <= y1 {
            log::warn!(
                "[recognize_cached_page] Invalid bbox for page {} mol {}: {:?}",
                page_idx,
                idx,
                d.bbox_pdf
            );
            continue;
        }

        let crop = img.crop_imm(x1, y1, x2 - x1, y2 - y1);
        let crop_filename = format!("page_{:04}_mol_{:03}.png", page_idx, idx);
        let crop_path = output_dir.join(&crop_filename);
        if let Err(e) = crop.save(&crop_path) {
            log::warn!(
                "[recognize_cached_page] Failed to save crop {}: {}",
                crop_path.display(),
                e
            );
            continue;
        }

        match molscribe(crop_path.to_str().unwrap_or(""), sidecar_url).await {
            Ok(ms) if ms.success && !ms.esmiles.is_empty() => {
                results.push(DetectedMolecule {
                    esmiles: ms.esmiles,
                    confidence: ms.confidence,
                    moldet_conf: d.conf_moldet,
                    page: page_idx,
                    crop_path: crop_path.to_string_lossy().to_string(),
                    bbox_pdf: d.bbox_pdf,
                });
            }
            Ok(_) => log::debug!(
                "[recognize_cached_page] MolScribe empty for page {} mol {}",
                page_idx,
                idx
            ),
            Err(e) => log::warn!(
                "[recognize_cached_page] MolScribe failed for page {} mol {}: {}",
                page_idx,
                idx,
                e
            ),
        }
    }

    log::info!(
        "[recognize_cached_page] Page {}: {} cached bboxes, {} recognized",
        page_idx,
        cached.iter().filter(|d| d.is_quick_scan).count(),
        results.len()
    );
    Ok(results)
}

// ---------------------------------------------------------------------------
// 快速 MoldDet 扫描（只检测分子 bbox，不识别 SMILES）
// ---------------------------------------------------------------------------

/// 单页快速扫描结果
#[derive(Debug, Clone, serde::Serialize)]
pub struct QuickMoldetPageResult {
    pub page: usize,
    pub has_molecule: bool,
    pub bbox_count: usize,
}

/// 单文档快速扫描结果
#[derive(Debug, Clone, serde::Serialize)]
pub struct QuickMoldetDocResult {
    pub path: String,
    pub doc_slug: String,
    pub doc_id: String,
    pub page_count: usize,
    pub pages: Vec<QuickMoldetPageResult>,
    pub pages_with_molecules: Vec<usize>,
    #[serde(default)]
    pub moldet_status: String,
    pub error: Option<String>,
}

/// 对单个 PDF 进行快速 MoldDet 扫描。
///
/// 与 `extract_molecules_from_pdf` 不同，此函数只调用 MolDet 检测 bbox，
/// 不调用 MolScribe 识别 SMILES，因此速度更快，适合“先标记可能存在分子的页面”。
///
/// 扫描结果会写入 `index/detections/<doc_slug>/page_<N>.json` 缓存，
/// 包含真实的 `bbox_pdf` 与 `conf_moldet`，但 `smiles`/`esmiles` 为空。
/// 完整识别可后续通过 `cached_extract_page` 或用户点击 bbox 触发。
pub async fn quick_moldet_scan_pdf(
    path: &str,
    project_root: &Path,
    sidecar_url: &str,
    doc_id: &str,
    batch_size: usize,
) -> Result<QuickMoldetDocResult, String> {
    let source_path = Path::new(path);
    let doc_slug = source_path
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("unknown")
        .to_string();

    let classified = classify_and_extract(path, false).await?;
    let page_count = classified.page_count.max(1);

    let mol_dir = tmp_output_dir(project_root, source_path, &doc_slug);
    std::fs::create_dir_all(&mol_dir)
        .map_err(|e| format!("Failed to create molecule dir: {}", e))?;

    let pdf_hash = crate::core::helpers::sha256_file(source_path).unwrap_or_default();
    let pdf_mtime = std::fs::metadata(source_path)
        .and_then(|m| m.modified())
        .ok()
        .and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok())
        .map(|d| d.as_secs_f64())
        .unwrap_or(0.0);

    let is_scanned = classified.parser == "mineru" || classified.parser == "mineru+cache";

    // 每个待检测的页面项：page_idx, 图片路径, 图片像素宽高。
    struct PageImage {
        page_idx: usize,
        path: PathBuf,
        width: u32,
        height: u32,
    }
    let mut page_images: Vec<PageImage> = Vec::new();

    if is_scanned {
        log::info!(
            "[quick_moldet_scan] Scanned PDF: processing {} embedded images from {}",
            classified.images.len(),
            path
        );

        for img_ref in classified.images.iter() {
            let img_path = if let Some(ref rp) = img_ref.rel_path {
                project_root.join(rp)
            } else {
                continue;
            };
            if !img_path.exists() {
                log::warn!(
                    "[quick_moldet_scan] Image not found: {}",
                    img_path.display()
                );
                continue;
            }

            let dims = image::open(&img_path)
                .map(|img| img.dimensions())
                .unwrap_or((0, 0));
            page_images.push(PageImage {
                page_idx: img_ref.page as usize,
                path: img_path,
                width: dims.0,
                height: dims.1,
            });
        }
    } else {
        log::info!(
            "[quick_moldet_scan] TextBased PDF: screenshot {} pages from {}",
            page_count,
            path
        );

        let page_numbers: Vec<u32> = (1..=page_count).map(|p| p as u32).collect();
        for batch_start in (0..page_numbers.len()).step_by(batch_size) {
            let batch_end = (batch_start + batch_size).min(page_numbers.len());
            let batch_pages: Vec<u32> = page_numbers[batch_start..batch_end].to_vec();

            match crate::parsers::pdf::sidecar_render::render_pages(
                path,
                &batch_pages,
                sidecar_url,
            )
            .await
            {
                Ok(screenshots) => {
                    for ss in screenshots {
                        let page_idx = ss.page_num as usize;
                        let page_img_path =
                            mol_dir.join(format!("page_{:04}_screenshot.png", page_idx));
                        if let Err(e) = std::fs::write(&page_img_path, &ss.image_bytes) {
                            log::warn!(
                                "[quick_moldet_scan] Failed to save screenshot page {}: {}",
                                page_idx,
                                e
                            );
                            continue;
                        }
                        page_images.push(PageImage {
                            page_idx,
                            path: page_img_path,
                            width: ss.width,
                            height: ss.height,
                        });
                    }
                }
                Err(e) => {
                    log::warn!(
                        "[quick_moldet_scan] Sidecar screenshot failed for batch {}-{}: {}",
                        batch_start + 1,
                        batch_end,
                        e
                    );
                }
            }
        }
    }

    let mut pages: Vec<QuickMoldetPageResult> = Vec::new();
    let mut pages_with_molecules: Vec<usize> = Vec::new();

    // 按 batch 进行 MoldDet 批量检测。
    let batch_size = batch_size.max(1);
    for batch_start in (0..page_images.len()).step_by(batch_size) {
        let batch_end = (batch_start + batch_size).min(page_images.len());
        let batch = &page_images[batch_start..batch_end];
        let paths: Vec<&str> = batch
            .iter()
            .map(|p| p.path.to_str().unwrap_or(""))
            .collect();

        match detect_batch_images(&paths, sidecar_url).await {
            Ok(batch_bboxes) => {
                for (img, bboxes) in batch.iter().zip(batch_bboxes.into_iter()) {
                    let has_molecule = !bboxes.is_empty();
                    if has_molecule {
                        pages_with_molecules.push(img.page_idx);
                    }
                    pages.push(QuickMoldetPageResult {
                        page: img.page_idx,
                        has_molecule,
                        bbox_count: bboxes.len(),
                    });

                    // 转换图像坐标 → PDF 坐标，并写入缓存。
                    if !pdf_hash.is_empty() && has_molecule {
                        let page_size = pdf_page_size_pts(source_path, img.page_idx - 1);
                        let detections: Vec<CachedDetection> = if let Some((pw, ph)) = page_size {
                            let scale = scale_from_page_size(pw, ph, img.width, img.height);
                            bboxes
                                .into_iter()
                                .map(|b| {
                                    let (x1, y1, x2, y2) =
                                        image_to_pdf_bbox((b.x1, b.y1, b.x2, b.y2), ph, scale);
                                    CachedDetection {
                                        bbox_pdf: [x1, y1, x2, y2],
                                        smiles: None,
                                        esmiles: None,
                                        conf_moldet: b.conf,
                                        conf_molscribe: 0.0,
                                        vlm_caption: None,
                                        vlm_esmiles: None,
                                        crop_relpath: None,
                                        is_quick_scan: true,
                                    }
                                })
                                .collect()
                        } else {
                            bboxes
                                .into_iter()
                                .map(|b| CachedDetection {
                                    bbox_pdf: [b.x1, b.y1, b.x2, b.y2],
                                    smiles: None,
                                    esmiles: None,
                                    conf_moldet: b.conf,
                                    conf_molscribe: 0.0,
                                    vlm_caption: None,
                                    vlm_esmiles: None,
                                    crop_relpath: None,
                                    is_quick_scan: true,
                                })
                                .collect()
                        };

                        let (cache, cache_key) =
                            detection_cache_for_pdf(project_root, source_path, &doc_slug);
                        let entry = PageDetection {
                            doc_id: cache_key.clone(),
                            page: img.page_idx,
                            pdf_hash: pdf_hash.clone(),
                            mtime: pdf_mtime,
                            detected_at: std::time::SystemTime::now()
                                .duration_since(std::time::UNIX_EPOCH)
                                .map(|d| d.as_secs_f64())
                                .unwrap_or(0.0),
                            schema_version: DETECTION_CACHE_SCHEMA_VERSION,
                            detections,
                        };
                        if let Err(e) = cache.put(&entry) {
                            log::warn!(
                                "[quick_moldet_scan] cache write failed for {} page {}: {}",
                                cache_key,
                                img.page_idx,
                                e
                            );
                        }
                    }
                }
            }
            Err(e) => {
                log::warn!(
                    "[quick_moldet_scan] detect_batch failed for batch {}-{}: {}",
                    batch_start + 1,
                    batch_end,
                    e
                );
            }
        }
    }

    pages.sort_by(|a, b| a.page.cmp(&b.page));
    pages_with_molecules.sort();
    pages_with_molecules.dedup();

    log::info!(
        "[quick_moldet_scan] {}: scanned {} pages, {} with molecules",
        path,
        pages.len(),
        pages_with_molecules.len()
    );

    Ok(QuickMoldetDocResult {
        path: path.to_string(),
        doc_slug,
        doc_id: doc_id.to_string(),
        page_count,
        pages,
        pages_with_molecules,
        moldet_status: String::new(),
        error: None,
    })
}

/// 从 PDF 中提取分子图像（MolDet + MolScribe）
///
/// 根据 PDF 类型选择不同策略：
/// - TextBased（如中国专利）：sidecar 渲染每页 → MolDet 检测 → 裁剪 → MolScribe
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
    let mol_dir = molecule_output_dir(project_root, source_path, doc_slug);

    std::fs::create_dir_all(&mol_dir)
        .map_err(|e| format!("Failed to create molecule dir: {}", e))?;

    let mut all_results = Vec::new();

    // PDF hash + mtime for the detection cache key. We re-hash on every
    // batch extract call, but a single batch re-reads at most one file,
    // so the cost is negligible. The on-demand path uses an in-memory
    // LRU to skip this on repeat calls within a session.
    let pdf_hash = crate::core::helpers::sha256_file(source_path).unwrap_or_default();
    let pdf_mtime = std::fs::metadata(source_path)
        .and_then(|m| m.modified())
        .ok()
        .and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok())
        .map(|d| d.as_secs_f64())
        .unwrap_or(0.0);

    // Detection cache for this document. For DocumentProject the key is the
    // doc_id; for legacy projects it is the PDF file stem.
    let (cache, cache_key) = detection_cache_for_pdf(project_root, source_path, doc_slug);

    if is_scanned {
        // Scanned: 使用 lopdf 提取的位图
        log::info!(
            "[extract_molecules] Scanned PDF: processing {} embedded images from {}",
            classified.images.len(),
            path
        );

        for (_idx, img_ref) in classified.images.iter().enumerate() {
            let img_path = if let Some(ref rp) = img_ref.rel_path {
                project_root.join(rp)
            } else {
                continue;
            };

            if !img_path.exists() {
                log::warn!(
                    "[extract_molecules] Image not found: {}",
                    img_path.display()
                );
                continue;
            }

            let page_idx = img_ref.page as i32;
            let output_dir = mol_dir.clone();
            let page_size = pdf_page_size_pts(source_path, (page_idx - 1).max(0) as usize);

            // Phase 5: 优先复用 quick-scan 缓存的 bbox，只跑 MolScribe。
            let mut used_cache = false;
            if !pdf_hash.is_empty() {
                if let Some(page_det) = cache.get(&cache_key, page_idx as usize, &pdf_hash) {
                    if page_det.detections.iter().any(|d| d.is_quick_scan) {
                        let cached = page_det.detections.clone();
                        match recognize_cached_page(
                            &img_path,
                            page_idx,
                            page_size,
                            sidecar_url,
                            &output_dir,
                            &cached,
                        )
                        .await
                        {
                            Ok(results) => {
                                merge_and_write_full_detections(
                                    &cache,
                                    &cache_key,
                                    page_idx as usize,
                                    &pdf_hash,
                                    pdf_mtime,
                                    page_det,
                                    &results,
                                    project_root,
                                );
                                all_results.extend(results);
                                used_cache = true;
                            }
                            Err(e) => {
                                log::warn!(
                                    "[extract_molecules] Cached recognition failed for page {}: {}",
                                    page_idx,
                                    e
                                );
                            }
                        }
                    }
                }
            }

            if used_cache {
                continue;
            }

            match process_page_image(
                img_path.to_str().unwrap_or(""),
                page_idx,
                sidecar_url,
                &output_dir,
                None, // scanned path: page dims not readily available
                None,
            )
            .await
            {
                Ok(results) => {
                    // Persist this page's detections to the detection cache.
                    // (Scanned PDFs may have multiple images per page; each
                    // call extends the same per-page entry.)
                    if !results.is_empty() && !pdf_hash.is_empty() {
                        write_detection_cache(
                            project_root,
                            source_path,
                            doc_slug,
                            page_idx as usize,
                            &pdf_hash,
                            pdf_mtime,
                            &results,
                        );
                    }
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
        // TextBased: sidecar PyMuPDF 截图每页
        log::info!(
            "[extract_molecules] TextBased PDF: screenshot {} pages from {}",
            classified.page_count,
            path
        );

        // 生成页码列表（1-indexed for sidecar）
        let page_numbers: Vec<u32> = (1..=classified.page_count).map(|p| p as u32).collect();

        // 分批截图（避免内存溢出，每批 10 页）
        let batch_size = 10usize;
        for batch_start in (0..page_numbers.len()).step_by(batch_size) {
            let batch_end = (batch_start + batch_size).min(page_numbers.len());
            let batch_pages: Vec<u32> = page_numbers[batch_start..batch_end].to_vec();

            match crate::parsers::pdf::sidecar_render::render_pages(
                path,
                &batch_pages,
                sidecar_url,
            )
            .await
            {
                Ok(screenshots) => {
                    for ss in screenshots {
                        let page_idx = ss.page_num as i32; // page_num is 1-indexed
                        let page_img_path =
                            mol_dir.join(format!("page_{:04}_screenshot.png", page_idx));
                        if let Err(e) = std::fs::write(&page_img_path, &ss.image_bytes) {
                            log::warn!(
                                "[extract_molecules] Failed to save screenshot page {}: {}",
                                page_idx,
                                e
                            );
                            continue;
                        }

                        let output_dir = mol_dir.clone();
                        // Sidecar 截图是 text-based PDF，页面尺寸优先从 PDF 读取。
                        let page_size =
                            pdf_page_size_pts(source_path, (page_idx - 1).max(0) as usize);
                        let (pw, ph) = page_size.unwrap_or((595.0_f64, 842.0_f64));

                        // Phase 5: 优先复用 quick-scan 缓存的 bbox。
                        let mut used_cache = false;
                        if !pdf_hash.is_empty() {
                            if let Some(page_det) =
                                cache.get(&cache_key, page_idx as usize, &pdf_hash)
                            {
                                if page_det.detections.iter().any(|d| d.is_quick_scan) {
                                    let cached = page_det.detections.clone();
                                    match recognize_cached_page(
                                        &page_img_path,
                                        page_idx,
                                        Some((pw, ph)),
                                        sidecar_url,
                                        &output_dir,
                                        &cached,
                                    )
                                    .await
                                    {
                                        Ok(results) => {
                                            merge_and_write_full_detections(
                                                &cache,
                                                &cache_key,
                                                page_idx as usize,
                                                &pdf_hash,
                                                pdf_mtime,
                                                page_det,
                                                &results,
                                                project_root,
                                            );
                                            all_results.extend(results);
                                            used_cache = true;
                                        }
                                        Err(e) => {
                                            log::warn!(
                                                "[extract_molecules] Cached recognition failed for page {}: {}",
                                                page_idx,
                                                e
                                            );
                                        }
                                    }
                                }
                            }
                        }

                        if used_cache {
                            continue;
                        }

                        match process_page_image(
                            page_img_path.to_str().unwrap_or(""),
                            page_idx,
                            sidecar_url,
                            &output_dir,
                            Some(pw),
                            Some(ph),
                        )
                        .await
                        {
                            Ok(results) => {
                                if !results.is_empty() && !pdf_hash.is_empty() {
                                    write_detection_cache(
                                        project_root,
                                        source_path,
                                        doc_slug,
                                        page_idx as usize,
                                        &pdf_hash,
                                        pdf_mtime,
                                        &results,
                                    );
                                }
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
                        "[extract_molecules] Page rendering failed for batch {}-{}: {}",
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
// MolDetect Coref 提取（替代 label_assoc 的空间邻近性方法）
// ---------------------------------------------------------------------------

/// 使用 MolDetect coref 模式提取分子-标号关联
///
/// 与 `extract_molecules_from_pdf` 类似，但使用 ML 模型自动检测
/// 分子和标识符的共指关系，替代基于规则的 label_assoc 方法。
///
/// # Arguments
/// - `path`: PDF 文件路径
/// - `classified`: 分类结果（包含页面信息和图像引用）
/// - `sidecar_url`: Python sidecar URL
/// - `project_root`: 项目根目录
///
/// # Returns
/// - `Vec<CorefMolecule>`: 分子-标号关联结果列表
pub async fn extract_molecules_with_coref(
    path: &str,
    classified: &ClassifyResult,
    sidecar_url: &str,
    project_root: &Path,
) -> Result<Vec<CorefMolecule>, String> {
    let is_scanned = classified.parser == "mineru" || classified.parser == "mineru+cache";

    // 确定输出目录
    let source_path = Path::new(path);
    let doc_slug = source_path
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("unknown");
    let mol_dir = molecule_output_dir(project_root, source_path, doc_slug);

    std::fs::create_dir_all(&mol_dir)
        .map_err(|e| format!("Failed to create molecule dir: {}", e))?;

    let mut all_molecules = Vec::new();

    if is_scanned {
        // Scanned: 使用 lopdf 提取的位图
        log::info!(
            "[extract_coref] Scanned PDF: processing {} embedded images from {}",
            classified.images.len(),
            path
        );

        for (_idx, img_ref) in classified.images.iter().enumerate() {
            let img_path = if let Some(ref rp) = img_ref.rel_path {
                project_root.join(rp)
            } else {
                continue;
            };

            if !img_path.exists() {
                log::warn!("[extract_coref] Image not found: {}", img_path.display());
                continue;
            }

            let page_idx = img_ref.page as i32;

            // 调用 coref 检测
            match detect_coref(
                img_path.to_str().unwrap_or(""),
                sidecar_url,
                true, // use_molscribe
                true, // use_ocr
            )
            .await
            {
                Ok(coref_result) => {
                    // 保存裁剪图像
                    let crop_dir = mol_dir.join(format!("page_{:04}", page_idx));
                    let _ = std::fs::create_dir_all(&crop_dir);

                    // 转换为 CorefMolecule（坐标转换需要图像尺寸）
                    // 对于 scanned PDF，图像尺寸从图像文件读取
                    if let Ok(img) = image::open(&img_path) {
                        let (img_w, img_h) = img.dimensions();
                        let mut molecules = coref_to_molecules(
                            &coref_result,
                            page_idx,
                            595.0, // 默认 A4 宽度
                            842.0, // 默认 A4 高度
                            img_w,
                            img_h,
                        );

                        // 保存裁剪图像并填充 crop_path
                        for (mol_idx, mol) in molecules.iter_mut().enumerate() {
                            // 找到分子对应的 bbox
                            if let Some(bbox) =
                                coref_result.bboxes.iter().find(|b| b.category_id == 1)
                            {
                                let [x1, y1, x2, y2] = bbox.bbox;
                                let x1_px = (x1 * img_w as f64) as u32;
                                let y1_px = (y1 * img_h as f64) as u32;
                                let x2_px = (x2 * img_w as f64) as u32;
                                let y2_px = (y2 * img_h as f64) as u32;

                                if x2_px > x1_px && y2_px > y1_px {
                                    let crop =
                                        img.crop_imm(x1_px, y1_px, x2_px - x1_px, y2_px - y1_px);
                                    let crop_filename = format!("mol_{:03}.png", mol_idx);
                                    let crop_path = crop_dir.join(&crop_filename);
                                    if let Err(e) = crop.save(&crop_path) {
                                        log::warn!("[extract_coref] Failed to save crop: {}", e);
                                    } else {
                                        mol.crop_path = crop_path.to_string_lossy().to_string();
                                    }
                                }
                            }
                        }

                        all_molecules.extend(molecules);
                    }
                }
                Err(e) => {
                    log::warn!(
                        "[extract_coref] Failed to process image {} (page {}): {}",
                        img_path.display(),
                        page_idx,
                        e
                    );
                }
            }
        }
    } else {
        // TextBased: sidecar PyMuPDF 截图每页
        log::info!(
            "[extract_coref] TextBased PDF: screenshot {} pages from {}",
            classified.page_count,
            path
        );

        // 生成页码列表（1-indexed for sidecar）
        let page_numbers: Vec<u32> = (1..=classified.page_count).map(|p| p as u32).collect();

        // 分批截图（避免内存溢出，每批 10 页）
        let batch_size = 10usize;
        for batch_start in (0..page_numbers.len()).step_by(batch_size) {
            let batch_end = (batch_start + batch_size).min(page_numbers.len());
            let batch_pages: Vec<u32> = page_numbers[batch_start..batch_end].to_vec();

            match crate::parsers::pdf::sidecar_render::render_pages(
                path,
                &batch_pages,
                sidecar_url,
            )
            .await
            {
                Ok(screenshots) => {
                    for ss in screenshots {
                        let page_idx = ss.page_num as i32; // page_num is 1-indexed
                        let page_img_path =
                            mol_dir.join(format!("page_{:04}_screenshot.png", page_idx));
                        if let Err(e) = std::fs::write(&page_img_path, &ss.image_bytes) {
                            log::warn!(
                                "[extract_coref] Failed to save screenshot page {}: {}",
                                page_idx,
                                e
                            );
                            continue;
                        }

                        // 调用 coref 检测
                        let (pw, ph) = (595.0_f64, 842.0_f64);
                        match detect_coref(
                            page_img_path.to_str().unwrap_or(""),
                            sidecar_url,
                            true, // use_molscribe
                            true, // use_ocr
                        )
                        .await
                        {
                            Ok(coref_result) => {
                                // 保存裁剪图像
                                let crop_dir = mol_dir.join(format!("page_{:04}", page_idx));
                                let _ = std::fs::create_dir_all(&crop_dir);

                                // 读取图像获取尺寸
                                if let Ok(img) = image::open(&page_img_path) {
                                    let (img_w, img_h) = img.dimensions();
                                    let mut molecules = coref_to_molecules(
                                        &coref_result,
                                        page_idx,
                                        pw,
                                        ph,
                                        img_w,
                                        img_h,
                                    );

                                    // 保存裁剪图像并填充 crop_path
                                    for (mol_idx, mol) in molecules.iter_mut().enumerate() {
                                        // 找到分子对应的 bbox
                                        if let Some(bbox) =
                                            coref_result.bboxes.iter().find(|b| b.category_id == 1)
                                        {
                                            let [x1, y1, x2, y2] = bbox.bbox;
                                            let x1_px = (x1 * img_w as f64) as u32;
                                            let y1_px = (y1 * img_h as f64) as u32;
                                            let x2_px = (x2 * img_w as f64) as u32;
                                            let y2_px = (y2 * img_h as f64) as u32;

                                            if x2_px > x1_px && y2_px > y1_px {
                                                let crop = img.crop_imm(
                                                    x1_px,
                                                    y1_px,
                                                    x2_px - x1_px,
                                                    y2_px - y1_px,
                                                );
                                                let crop_filename =
                                                    format!("mol_{:03}.png", mol_idx);
                                                let crop_path = crop_dir.join(&crop_filename);
                                                if let Err(e) = crop.save(&crop_path) {
                                                    log::warn!(
                                                        "[extract_coref] Failed to save crop: {}",
                                                        e
                                                    );
                                                } else {
                                                    mol.crop_path =
                                                        crop_path.to_string_lossy().to_string();
                                                }
                                            }
                                        }
                                    }

                                    all_molecules.extend(molecules);
                                }
                            }
                            Err(e) => {
                                log::warn!(
                                    "[extract_coref] Failed to process screenshot page {}: {}",
                                    page_idx,
                                    e
                                );
                            }
                        }
                    }
                }
                Err(e) => {
                    log::warn!(
                        "[extract_coref] Page rendering failed for batch {}-{}: {}",
                        batch_start + 1,
                        batch_end,
                        e
                    );
                }
            }
        }
    }

    log::info!(
        "[extract_coref] Total molecules with labels from {}: {}",
        path,
        all_molecules.len()
    );

    Ok(all_molecules)
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
    /// MoleCode (Mermaid graph text) — auto-generated from E-SMILES
    /// (or bare SMILES) so the frontend can render the molecular
    /// structure inline without re-running the chem pipeline.
    /// `None` if the SMILES parse failed or the converter returned an
    /// error (the rest of the entry is still useful).
    #[serde(skip_serializing_if = "Option::is_none")]
    molcode: Option<String>,
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
    std::fs::create_dir_all(&mol_dir).map_err(|e| format!("Failed to create output dir: {}", e))?;

    log::info!(
        "[workflow] Starting extraction: {} → {}",
        pdf_path,
        base_dir.display()
    );

    // Stage 1: 文本提取 + 分类
    let mut classified = classify_and_extract(pdf_path, true).await?;

    // First pass at text.md: enrich inline `![]()` references and add
    // the "## Extracted Images" appendix. Descriptions are still the
    // generic "Image extracted from page N" — VLM captions are
    // unavailable until Stage 2 (extract_molecules_from_pdf) populates
    // the detection cache.
    let augmented_text = crate::parsers::pipeline::markdown_augment::augment_markdown_with_images(
        &classified.text,
        &classified.images,
        Some(&classified.ocr_blocks),
    );

    // 写入 text.md (first pass — without VLM captions)
    let text_path = base_dir.join("text.md");
    std::fs::write(&text_path, &augmented_text)
        .map_err(|e| format!("Failed to write text.md: {}", e))?;

    log::info!(
        "[workflow] Text extracted: {} pages, {} chars, parser={}",
        classified.page_count,
        classified.text.len(),
        classified.parser
    );

    // Stage 2: 分子图像检测 + 识别（同时把 VLM 写进 detection cache）
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

    log::info!("[workflow] Detected {} molecules", detected.len());

    // Second pass at text.md: pull VLM captions out of the detection
    // cache the Stage 2 just wrote, then re-augment. The detection
    // cache key uses the PDF file stem (matches the molecules/<stem>/
    // convention), and the per-PDF hash for invalidation.
    let doc_slug = Path::new(pdf_path)
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("unknown");
    let pdf_hash = crate::core::helpers::sha256_file(Path::new(pdf_path)).unwrap_or_default();
    let n_captioned =
        crate::parsers::pipeline::markdown_augment::populate_descriptions_from_detection_cache(
            &mut classified.images,
            &base_dir,
            doc_slug,
            &pdf_hash,
        );
    if n_captioned > 0 {
        log::info!(
            "[workflow] Injected {} VLM caption(s) into markdown augmentation",
            n_captioned
        );
        let enriched_text =
            crate::parsers::pipeline::markdown_augment::augment_markdown_with_images(
                &classified.text,
                &classified.images,
                Some(&classified.ocr_blocks),
            );
        std::fs::write(&text_path, &enriched_text)
            .map_err(|e| format!("Failed to re-write text.md: {}", e))?;
    }

    // Stage 3: 生成 manifest.json
    let molecules: Vec<MoleculeEntry> = detected
        .iter()
        .enumerate()
        .map(|(i, mol)| {
            // 裁剪图片文件名格式: page_XXXX_mol_YYY.png
            let image_file = format!("page_{:04}_mol_{:03}.png", mol.page, i);
            let (smiles, esmiles_opt, _tags) = separate_esmiles_layers(&mol.esmiles);
            let mol_name = format!("IMG-{}-P{}", pdf_name, mol.page);
            // Auto-generate MoleCode (Mermaid graph) from E-SMILES, falling
            // back to bare SMILES. Failures are non-fatal — the entry is
            // still emitted with `molcode: None` so the rest of the
            // pipeline is unaffected.
            let molcode =
                esmiles_to_molecode_opt(esmiles_opt.as_deref().unwrap_or(&smiles), &mol_name);
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

/// Best-effort wrapper around `esmiles_to_molecode` for the manifest
/// generation path. Returns `None` on parse failure or empty input so
/// the rest of `MoleculeEntry` is still useful.
fn esmiles_to_molecode_opt(input: &str, name: &str) -> Option<String> {
    let trimmed = input.trim();
    if trimmed.is_empty() {
        return None;
    }
    match crate::core::chem::chem::esmiles_to_molecode(trimmed, name) {
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
