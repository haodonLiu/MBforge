//! Quick MoldDet scan service.
//!
//! Performs a fast page-level molecule detection pass over a PDF. The service
//! only returns bounding boxes and confidence scores; it does **not** run
//! MolScribe SMILES recognition. This matches the legacy `quick_moldet_scan_pdf`
//! behaviour while exposing a simplified, v2-compatible API.

use std::path::{Path, PathBuf};

use image::GenericImageView;
use serde::{Deserialize, Serialize};

use crate::core::config::constants::sidecar_url;
use crate::core::config::settings::AppConfig;
use crate::parsers::chem::vlm_chem::{detect_batch, Bbox};
use crate::parsers::doc_types::ImageRef;
use crate::parsers::pdf::images::{image_to_pdf_bbox, pdf_page_size_pts, scale_from_page_size};
use crate::parsers::pdf::sidecar_render::render_pages;
use crate::parsers::pipeline::legacy::{classify_and_extract, find_project_root};

/// Per-page detection result for a quick MoldDet scan.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QuickMoldetPageResult {
    /// 1-based page index.
    pub page: usize,
    /// Detected molecule regions in PDF coordinates (x, y, width, height).
    pub bboxes: Vec<MoldetBBox>,
}

/// Axis-aligned bounding box returned by the quick MoldDet scan.
///
/// Coordinates are in PDF page space when the original page size can be
/// determined; otherwise they fall back to image pixel coordinates.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MoldetBBox {
    pub x: f32,
    pub y: f32,
    pub w: f32,
    pub h: f32,
    pub conf: f32,
}

/// Document-level quick MoldDet scan result.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QuickMoldetDocResult {
    /// Source PDF path (as provided by the caller).
    pub source: String,
    /// Per-page detection results.
    pub pages: Vec<QuickMoldetPageResult>,
}

/// Internal holder for a page image ready for MoldDet inference.
struct PageImage {
    page_idx: usize,
    path: PathBuf,
    width: u32,
    height: u32,
}

/// Run a quick MoldDet scan over `path`, returning page-level bounding boxes.
///
/// # Behaviour
/// - Text-based PDFs are rendered to images via the Python sidecar.
/// - Scanned PDFs reuse embedded/page images produced during classification.
/// - Bounding boxes are converted to PDF coordinates whenever page size
///   information is available.
/// - The service does **not** write to the detection cache; callers that need
///   caching should persist the returned `MoldetBBox` values themselves.
pub async fn quick_scan_pdf(path: &Path) -> Result<QuickMoldetDocResult, String> {
    let path_str = path
        .to_str()
        .ok_or_else(|| format!("PDF path is not valid UTF-8: {}", path.display()))?;

    if !path.exists() {
        return Err(format!("PDF not found: {}", path.display()));
    }

    let project_root = find_project_root(path, None);
    let classified = classify_and_extract(path_str, false).await?;
    let page_count = classified.page_count.max(1);
    let is_scanned = classified.parser == "mineru" || classified.parser == "mineru+cache";

    log::info!(
        "[quick_scan_pdf] {}: parser={}, pages={}, scanned={}",
        path.display(),
        classified.parser,
        page_count,
        is_scanned
    );

    let (page_images, _tmp_dir) = if is_scanned {
        (
            collect_scanned_page_images(&classified.images, project_root.as_deref()).await,
            None,
        )
    } else {
        let (images, tmp) = render_text_page_images(path_str, page_count).await?;
        (images, Some(tmp))
    };

    let mut pages: Vec<QuickMoldetPageResult> = Vec::new();
    let batch_size = AppConfig::load().moldet.moldet_batch_size.max(1);

    for batch_start in (0..page_images.len()).step_by(batch_size) {
        let batch_end = (batch_start + batch_size).min(page_images.len());
        let batch = &page_images[batch_start..batch_end];
        let paths: Vec<&str> = batch
            .iter()
            .map(|p| p.path.to_str().unwrap_or(""))
            .collect();

        match detect_batch(&paths, &sidecar_url()).await {
            Ok(batch_bboxes) => {
                for (img, bboxes) in batch.iter().zip(batch_bboxes.into_iter()) {
                    pages.push(build_page_result(path, img, bboxes));
                }
            }
            Err(e) => {
                log::warn!(
                    "[quick_scan_pdf] detect_batch failed for batch {}-{} of {}: {}",
                    batch_start + 1,
                    batch_end,
                    path.display(),
                    e
                );
            }
        }
    }

    pages.sort_by(|a, b| a.page.cmp(&b.page));

    log::info!(
        "[quick_scan_pdf] {}: scanned {} pages, {} with detections",
        path.display(),
        pages.len(),
        pages.iter().filter(|p| !p.bboxes.is_empty()).count()
    );

    Ok(QuickMoldetDocResult {
        source: path_str.to_string(),
        pages,
    })
}

/// Collect page images from a scanned PDF using the images already extracted
/// during classification.
async fn collect_scanned_page_images(
    images: &[ImageRef],
    project_root: Option<&Path>,
) -> Vec<PageImage> {
    let mut page_images: Vec<PageImage> = Vec::new();

    for img_ref in images.iter() {
        let img_path = if let Some(ref rp) = img_ref.rel_path {
            project_root.map(|root| root.join(rp))
        } else {
            None
        };

        let Some(img_path) = img_path else {
            continue;
        };

        if !img_path.exists() {
            log::warn!(
                "[quick_scan_pdf] Scanned image not found: {}",
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
            page_idx: img_ref.page as usize,
            path: img_path,
            width: dims.0,
            height: dims.1,
        });
    }

    page_images
}

/// Render all pages of a text-based PDF to temporary PNG images.
///
/// Returns the collected page images together with the temporary directory
/// holder. The caller must keep `_tmp` alive until MoldDet inference finishes.
async fn render_text_page_images(
    pdf_path: &str,
    page_count: usize,
) -> Result<(Vec<PageImage>, tempfile::TempDir), String> {
    let tmp = tempfile::tempdir().map_err(|e| format!("failed to create temp dir: {e}"))?;
    let page_numbers: Vec<u32> = (1..=page_count).map(|p| p as u32).collect();
    let batch_size = 10usize;
    let mut page_images: Vec<PageImage> = Vec::new();

    for batch_start in (0..page_numbers.len()).step_by(batch_size) {
        let batch_end = (batch_start + batch_size).min(page_numbers.len());
        let batch_pages: Vec<u32> = page_numbers[batch_start..batch_end].to_vec();

        match render_pages(pdf_path, &batch_pages, &sidecar_url()).await {
            Ok(screenshots) => {
                for ss in screenshots {
                    let page_idx = ss.page_num as usize;
                    let page_img_path = tmp.path().join(format!("page_{:04}_screenshot.png", page_idx));
                    if let Err(e) = std::fs::write(&page_img_path, &ss.image_bytes) {
                        log::warn!(
                            "[quick_scan_pdf] Failed to save screenshot page {}: {}",
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
                    "[quick_scan_pdf] Sidecar screenshot failed for batch {}-{}: {}",
                    batch_start + 1,
                    batch_end,
                    e
                );
            }
        }
    }

    Ok((page_images, tmp))
}

/// Convert sidecar image bboxes into page result entries, normalising to PDF
/// coordinates when page size is available.
fn build_page_result(pdf_path: &Path, img: &PageImage, bboxes: Vec<Bbox>) -> QuickMoldetPageResult {
    let page_size = pdf_page_size_pts(pdf_path, img.page_idx.saturating_sub(1));

    let converted: Vec<MoldetBBox> = if let Some((pw, ph)) = page_size {
        let scale = scale_from_page_size(pw, ph, img.width, img.height);
        bboxes
            .into_iter()
            .map(|b| {
                let (x1, y1, x2, y2) = image_to_pdf_bbox((b.x1, b.y1, b.x2, b.y2), ph, scale);
                MoldetBBox {
                    x: x1 as f32,
                    y: y1 as f32,
                    w: (x2 - x1) as f32,
                    h: (y2 - y1) as f32,
                    conf: b.conf as f32,
                }
            })
            .collect()
    } else {
        bboxes
            .into_iter()
            .map(|b| MoldetBBox {
                x: b.x1 as f32,
                y: b.y1 as f32,
                w: (b.x2 - b.x1) as f32,
                h: (b.y2 - b.y1) as f32,
                conf: b.conf as f32,
            })
            .collect()
    };

    QuickMoldetPageResult {
        page: img.page_idx,
        bboxes: converted,
    }
}
