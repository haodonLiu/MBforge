//! Quick MoldDet scan service.
//!
//! Performs a fast page-level molecule detection pass over a PDF. The service
//! only returns bounding-box presence/counts and does **not** run MolScribe
//! SMILES recognition. The public types and entry point are kept identical to
//! the legacy implementation so existing callers can be switched over without
//! changes.

use std::path::{Path, PathBuf};

use image::GenericImageView;
use serde::{Deserialize, Serialize};

use crate::core::config::constants::{MOLECULES_DIR, PROJECTS_DIR, PROJECT_SOURCE_FILE};
use crate::core::document::detection_cache::{
    Detection as CachedDetection, DetectionCache, PageDetection, DETECTION_CACHE_SCHEMA_VERSION,
};
use crate::parsers::chem::vlm_chem::{detect_batch, Bbox};
use crate::parsers::pdf::images::{image_to_pdf_bbox, pdf_page_size_pts, scale_from_page_size};
use crate::parsers::pdf::sidecar_render::render_pages;
use crate::parsers::pipeline::models::extracted::ImageRef;
use crate::parsers::pipeline::services::images::ImageService;
use crate::parsers::pipeline::services::inspector::InspectorService;
use crate::parsers::pipeline::services::source::SourceResolver;

/// Per-page quick MoldDet scan result.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QuickMoldetPageResult {
    /// 1-based page index.
    pub page: usize,
    /// Whether at least one molecule bounding box was detected on this page.
    pub has_molecule: bool,
    /// Number of molecule bounding boxes detected on this page.
    pub bbox_count: usize,
}

/// Document-level quick MoldDet scan result.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QuickMoldetDocResult {
    /// Absolute path to the source PDF.
    pub path: String,
    /// PDF file stem used for legacy cache keys.
    pub doc_slug: String,
    /// Document identifier (passed through from the caller).
    pub doc_id: String,
    /// Total number of pages in the document.
    pub page_count: usize,
    /// Per-page scan results.
    pub pages: Vec<QuickMoldetPageResult>,
    /// 1-based page numbers that contain at least one molecule bbox.
    pub pages_with_molecules: Vec<usize>,
    /// MoldDet status summary (`"no_molecule"`, `"has_molecule"`, etc.).
    #[serde(default)]
    pub moldet_status: String,
    /// Error message when the scan fails at the document level.
    pub error: Option<String>,
}

/// Internal holder for a page image ready for MoldDet inference.
struct PageImage {
    page_idx: usize,
    path: PathBuf,
    width: u32,
    height: u32,
}

/// Run a quick MoldDet scan over a single PDF.
///
/// This mirrors the legacy quick-scan signature and behaviour:
/// only molecule bounding boxes are detected (no MolScribe), results are
/// written to the detection cache as quick-scan entries, and the returned
/// `QuickMoldetDocResult` uses the exact legacy field set.
///
/// # Arguments
/// * `path` - PDF file path.
/// * `project_root` - MBForge project root directory.
/// * `sidecar_url` - Python sidecar base URL.
/// * `doc_id` - Document identifier used by callers.
/// * `batch_size` - Number of pages to send to the sidecar in one batch.
pub async fn quick_scan_pdf(
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

    // Resolve project root via the v2 SourceResolver (legacy `find_project_root`
    // replacement). Fall back to the caller-supplied project root so the scan
    // can still proceed when root discovery fails.
    let resolved_root = SourceResolver::new()
        .resolve_project_root(source_path, Some(project_root))
        .unwrap_or_else(|_| project_root.to_path_buf());

    // Use the v2 InspectorService to obtain page count and raw text (legacy
    // `classify_and_extract` replacement; OCR is disabled for quick scans).
    let inspector = InspectorService::new();
    let extracted = inspector
        .extract(source_path)
        .await
        .map_err(|e| format!("PDF inspection failed: {}", e))?;

    let page_count = extracted.page_count.max(1);
    let is_scanned = extracted.raw_text.len() < 100 && extracted.page_count > 0;

    // Create the temporary working directory. Legacy layout:
    // - DocumentProject: `projects/<doc_id>/cache/tmp/`
    // - Legacy: `molecules/<doc_slug>/`
    let tmp_dir = tmp_output_dir(&resolved_root, source_path, &doc_slug);
    std::fs::create_dir_all(&tmp_dir)
        .map_err(|e| format!("Failed to create molecule dir: {}", e))?;

    let pdf_hash = crate::core::helpers::sha256_file(source_path).unwrap_or_default();
    let pdf_mtime = std::fs::metadata(source_path)
        .and_then(|m| m.modified())
        .ok()
        .and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok())
        .map(|d| d.as_secs_f64())
        .unwrap_or(0.0);

    // Extract and persist embedded images so scanned PDFs have on-disk image
    // references to pass to MolDet. This matches the legacy side effect of
    // `classify_and_extract`.
    let images = extract_and_persist_images(source_path, &resolved_root).await?;

    let page_images = if is_scanned {
        log::info!(
            "[quick_scan] Scanned PDF: processing {} embedded images from {}",
            images.len(),
            path
        );
        collect_scanned_page_images(&images, &resolved_root).await
    } else {
        log::info!(
            "[quick_scan] TextBased PDF: screenshot {} pages from {}",
            page_count,
            path
        );
        render_text_page_images(path, page_count, sidecar_url, &tmp_dir).await?
    };

    let mut pages: Vec<QuickMoldetPageResult> = Vec::new();
    let mut pages_with_molecules: Vec<usize> = Vec::new();

    let batch_size = batch_size.max(1);
    for batch_start in (0..page_images.len()).step_by(batch_size) {
        let batch_end = (batch_start + batch_size).min(page_images.len());
        let batch = &page_images[batch_start..batch_end];
        let paths: Vec<&str> = batch
            .iter()
            .map(|p| p.path.to_str().unwrap_or(""))
            .collect();

        match detect_batch(&paths, sidecar_url).await {
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

                    // Convert image coordinates to PDF coordinates and write
                    // quick-scan entries to the detection cache.
                    if !pdf_hash.is_empty() && has_molecule {
                        write_quick_scan_cache(
                            &resolved_root,
                            source_path,
                            &doc_slug,
                            img.page_idx,
                            &pdf_hash,
                            pdf_mtime,
                            &bboxes,
                            img.width,
                            img.height,
                        );
                    }
                }
            }
            Err(e) => {
                log::warn!(
                    "[quick_scan] detect_batch failed for batch {}-{}: {}",
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
        "[quick_scan] {}: scanned {} pages, {} with molecules",
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

/// Extract embedded images from the PDF and persist them under the project root.
async fn extract_and_persist_images(
    source_path: &Path,
    project_root: &Path,
) -> Result<Vec<ImageRef>, String> {
    let images = ImageService::new();
    let tmp = tempfile::tempdir().map_err(|e| format!("failed to create temp dir: {e}"))?;

    let extracted = images
        .extract_embedded_images(source_path, tmp.path())
        .await
        .map_err(|e| format!("image extraction failed: {}", e))?;

    Ok(images.persist_extracted_images(source_path, project_root, &extracted))
}

/// Collect page images from a scanned PDF using the images extracted during
/// classification.
async fn collect_scanned_page_images(
    images: &[ImageRef],
    project_root: &Path,
) -> Vec<PageImage> {
    let mut page_images: Vec<PageImage> = Vec::new();

    for img_ref in images.iter() {
        let img_path = if let Some(ref rp) = img_ref.rel_path {
            Some(project_root.join(rp))
        } else {
            None
        };

        let Some(img_path) = img_path else {
            continue;
        };

        if !img_path.exists() {
            log::warn!(
                "[quick_scan] Image not found: {}",
                img_path.display()
            );
            continue;
        }

        let dims = tokio::task::spawn_blocking({
            let img_path = img_path.clone();
            move || image::open(&img_path).map(|img| img.dimensions()).unwrap_or((0, 0))
        })
        .await
        .unwrap_or((0, 0));

        page_images.push(PageImage {
            page_idx: img_ref.page,
            path: img_path,
            width: dims.0,
            height: dims.1,
        });
    }

    page_images
}

/// Render all pages of a text-based PDF to temporary PNG images.
async fn render_text_page_images(
    pdf_path: &str,
    page_count: usize,
    sidecar_url: &str,
    tmp_dir: &Path,
) -> Result<Vec<PageImage>, String> {
    let page_numbers: Vec<u32> = (1..=page_count).map(|p| p as u32).collect();
    let render_batch_size = 10usize;
    let mut page_images: Vec<PageImage> = Vec::new();

    for batch_start in (0..page_numbers.len()).step_by(render_batch_size) {
        let batch_end = (batch_start + render_batch_size).min(page_numbers.len());
        let batch_pages: Vec<u32> = page_numbers[batch_start..batch_end].to_vec();

        match render_pages(pdf_path, &batch_pages, sidecar_url).await {
            Ok(screenshots) => {
                for ss in screenshots {
                    let page_idx = ss.page_num as usize;
                    let page_img_path = tmp_dir.join(format!("page_{:04}_screenshot.png", page_idx));
                    if let Err(e) = std::fs::write(&page_img_path, &ss.image_bytes) {
                        log::warn!(
                            "[quick_scan] Failed to save screenshot page {}: {}",
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
                    "[quick_scan] Sidecar screenshot failed for batch {}-{}: {}",
                    batch_start + 1,
                    batch_end,
                    e
                );
            }
        }
    }

    Ok(page_images)
}

/// Convert MoldDet image bboxes into quick-scan cache detections and persist them.
fn write_quick_scan_cache(
    project_root: &Path,
    source_path: &Path,
    doc_slug: &str,
    page: usize,
    pdf_hash: &str,
    pdf_mtime: f64,
    bboxes: &[Bbox],
    img_width: u32,
    img_height: u32,
) {
    let page_size = pdf_page_size_pts(source_path, page.saturating_sub(1));

    let detections: Vec<CachedDetection> = if let Some((pw, ph)) = page_size {
        let scale = scale_from_page_size(pw, ph, img_width, img_height);
        bboxes
            .iter()
            .map(|b| {
                let (x1, y1, x2, y2) = image_to_pdf_bbox((b.x1, b.y1, b.x2, b.y2), ph, scale);
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
            .iter()
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

    let (cache, cache_key) = detection_cache_for_pdf(project_root, source_path, doc_slug);
    let entry = PageDetection {
        doc_id: cache_key,
        page,
        pdf_hash: pdf_hash.to_string(),
        mtime: pdf_mtime,
        detected_at: crate::core::helpers::now_secs_f64(),
        schema_version: DETECTION_CACHE_SCHEMA_VERSION,
        detections,
    };

    if let Err(e) = cache.put(&entry) {
        log::warn!(
            "[quick_scan] cache write failed for {} page {}: {}",
            entry.doc_id,
            page,
            e
        );
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

/// Return the detection cache and cache key for a PDF.
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
