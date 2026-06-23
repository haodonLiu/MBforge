//! Molecule extraction service for the PDF processing pipeline.
//!
//! This service detects molecular regions in PDF pages using MolDet and
//! recognizes each region with MolScribe. It builds pipeline-v2
//! [`DetectedMoleculeResult`] entries for the enrichment stage.

use std::path::{Path, PathBuf};

use crate::core::config::constants::{MOLECULES_DIR, PROJECTS_DIR, PROJECT_SOURCE_FILE};
use crate::core::helpers::assert_within_root_allow_missing;
use crate::parsers::chem::vlm_chem::{process_page_image, DetectedMolecule};
use crate::parsers::pdf::images::pdf_page_size_pts;
use crate::parsers::pdf::sidecar_render::render_pages;
use crate::parsers::pipeline::error::{EnrichError, PipelineError};
use crate::parsers::pipeline::models::enriched::DetectedMoleculeResult;
use crate::parsers::pipeline::models::extracted::{ExtractedDocument, ImageRef};
use crate::parsers::pipeline::services::images::ImageService;

/// Service for detecting and recognizing molecules in a PDF document.
#[derive(Debug, Clone)]
pub struct MoleculeService {
    /// URL of the Python sidecar providing MolDet / MolScribe backends.
    pub sidecar_url: String,
}

impl MoleculeService {
    /// Creates a new [`MoleculeService`] pointing at the given sidecar URL.
    ///
    /// # Arguments
    /// - `sidecar_url`: Base URL of the Python sidecar (e.g. `http://127.0.0.1:18792`).
    pub fn new(sidecar_url: impl Into<String>) -> Self {
        Self {
            sidecar_url: sidecar_url.into(),
        }
    }

    /// Extracts molecules from `path` using the already extracted document metadata.
    ///
    /// `path` is expected to be the source document path already validated by
    /// the caller. The service uses `ImageService` for embedded images on scanned
    /// PDFs and the sidecar page renderer for text-based PDFs, then calls MolDet
    /// and MolScribe to produce the final molecule list.
    ///
    /// # Arguments
    /// - `path`: Path to the source PDF file.
    /// - `extracted`: Extraction-stage output containing text, images, and parser info.
    /// - `project_root`: Project root directory used to persist cropped molecule images.
    ///
    /// # Returns
    /// A list of [`DetectedMoleculeResult`] entries, one per recognized molecule image.
    pub async fn extract(
        &self,
        path: &str,
        extracted: &ExtractedDocument,
        project_root: &Path,
    ) -> Result<Vec<DetectedMoleculeResult>, PipelineError> {
        let source_path = Path::new(path);
        let doc_slug = source_path
            .file_stem()
            .and_then(|s| s.to_str())
            .unwrap_or("unknown");

        let mol_dir = molecule_output_dir(project_root, source_path, doc_slug)
            .map_err(|e| PipelineError::Enrich(EnrichError::MoleculeServiceFailed { detail: e }))?;
        std::fs::create_dir_all(&mol_dir).map_err(|e| {
            PipelineError::Enrich(EnrichError::MoleculeServiceFailed {
                detail: format!("failed to create molecule dir: {}", e),
            })
        })?;

        let is_scanned = extracted.parser == "mineru" || extracted.parser == "mineru+cache";

        let detected = if is_scanned {
            self.extract_from_scanned(source_path, project_root, extracted, &mol_dir)
                .await
        } else {
            self.extract_from_text(source_path, extracted, &mol_dir).await
        }
        .map_err(|e| PipelineError::Enrich(EnrichError::MoleculeServiceFailed { detail: e }))?;

        Ok(detected.into_iter().map(into_detected_result).collect())
    }

    /// Extract molecules from a scanned PDF using embedded/MinerU images.
    ///
    /// Embedded images are refreshed through [`ImageService`] so that on-disk
    /// paths are guaranteed to exist, then each image is passed to MolDet +
    /// MolScribe via [`process_page_image`].
    async fn extract_from_scanned(
        &self,
        source_path: &Path,
        project_root: &Path,
        extracted: &ExtractedDocument,
        mol_dir: &Path,
    ) -> Result<Vec<DetectedMolecule>, String> {
        let images = extract_scanned_images(source_path, project_root, extracted).await?;

        log::info!(
            "[molecule_service] Scanned PDF: processing {} embedded images from {}",
            images.len(),
            source_path.display()
        );

        let mut all_results = Vec::new();
        for img_ref in images {
            let Some(img_path) = resolve_image_path(project_root, &img_ref) else {
                continue;
            };
            if !img_path.exists() {
                log::warn!(
                    "[molecule_service] Image not found: {}",
                    img_path.display()
                );
                continue;
            }

            let page_idx = img_ref.page as i32;
            let page_size = pdf_page_size_pts(source_path, (page_idx - 1).max(0) as usize);
            let (pw, ph) = page_size.unzip();

            match process_page_image(
                img_path.to_str().unwrap_or(""),
                page_idx,
                &self.sidecar_url,
                mol_dir,
                pw,
                ph,
            )
            .await
            {
                Ok(results) => all_results.extend(results),
                Err(e) => {
                    log::warn!(
                        "[molecule_service] Failed to process image {} (page {}): {}",
                        img_path.display(),
                        page_idx,
                        e
                    );
                }
            }
        }

        Ok(all_results)
    }

    /// Extract molecules from a text-based PDF by rendering each page.
    ///
    /// Pages are rendered through the Python sidecar in batches of 10, saved to
    /// the molecule output directory, and then processed with MolDet + MolScribe.
    async fn extract_from_text(
        &self,
        source_path: &Path,
        extracted: &ExtractedDocument,
        mol_dir: &Path,
    ) -> Result<Vec<DetectedMolecule>, String> {
        let path_str = source_path.to_string_lossy().to_string();
        let page_count = extracted.page_count.max(1);

        log::info!(
            "[molecule_service] TextBased PDF: screenshot {} pages from {}",
            page_count,
            path_str
        );

        let page_numbers: Vec<u32> = (1..=page_count).map(|p| p as u32).collect();
        let batch_size = 10usize;
        let mut all_results = Vec::new();

        for batch_start in (0..page_numbers.len()).step_by(batch_size) {
            let batch_end = (batch_start + batch_size).min(page_numbers.len());
            let batch_pages: Vec<u32> = page_numbers[batch_start..batch_end].to_vec();

            match render_pages(&path_str, &batch_pages, &self.sidecar_url).await {
                Ok(screenshots) => {
                    for ss in screenshots {
                        let page_idx = ss.page_num as i32;
                        let page_img_path =
                            mol_dir.join(format!("page_{:04}_screenshot.png", page_idx));
                        if let Err(e) = std::fs::write(&page_img_path, &ss.image_bytes) {
                            log::warn!(
                                "[molecule_service] Failed to save screenshot page {}: {}",
                                page_idx,
                                e
                            );
                            continue;
                        }

                        let page_size =
                            pdf_page_size_pts(source_path, (page_idx - 1).max(0) as usize);
                        let (pw, ph) = page_size.unwrap_or((595.0_f64, 842.0_f64));

                        match process_page_image(
                            page_img_path.to_str().unwrap_or(""),
                            page_idx,
                            &self.sidecar_url,
                            mol_dir,
                            Some(pw),
                            Some(ph),
                        )
                        .await
                        {
                            Ok(results) => all_results.extend(results),
                            Err(e) => {
                                log::warn!(
                                    "[molecule_service] Failed to process screenshot page {}: {}",
                                    page_idx,
                                    e
                                );
                            }
                        }
                    }
                }
                Err(e) => {
                    log::warn!(
                        "[molecule_service] Page rendering failed for batch {}-{}: {}",
                        batch_start + 1,
                        batch_end,
                        e
                    );
                }
            }
        }

        Ok(all_results)
    }
}

impl Default for MoleculeService {
    fn default() -> Self {
        Self::new("")
    }
}

/// Extract embedded images from the PDF and persist them under the project root.
///
/// If extraction fails, the images already present in `extracted` are used as a
/// fallback so that downstream processing can still proceed.
async fn extract_scanned_images(
    source_path: &Path,
    project_root: &Path,
    extracted: &ExtractedDocument,
) -> Result<Vec<ImageRef>, String> {
    let service = ImageService::new();
    let tmp = tempfile::tempdir().map_err(|e| format!("failed to create temp dir: {e}"))?;

    match service.extract_embedded_images(source_path, tmp.path()).await {
        Ok(extracted_images) => Ok(service.persist_extracted_images(
            source_path,
            project_root,
            &extracted_images,
        )),
        Err(e) => {
            log::warn!(
                "[molecule_service] ImageService extraction failed ({}), falling back to extracted images",
                e
            );
            Ok(extracted.images.clone())
        }
    }
}

/// Resolve an [`ImageRef`] to an absolute path inside the project root.
fn resolve_image_path(project_root: &Path, img_ref: &ImageRef) -> Option<PathBuf> {
    let rel = img_ref.rel_path.as_ref().or(Some(&img_ref.filename))?;
    crate::core::helpers::safe_join(project_root, rel).ok()
}

/// Convert a raw detected molecule into the pipeline-v2 result type.
fn into_detected_result(m: DetectedMolecule) -> DetectedMoleculeResult {
    DetectedMoleculeResult {
        esmiles: m.esmiles,
        confidence: m.confidence,
        moldet_conf: m.moldet_conf,
        page: m.page.max(0) as usize,
        crop_path: m.crop_path,
        bbox_pdf: m.bbox_pdf,
    }
}

/// Return the molecule output directory for a PDF.
///
/// - DocumentProject: `projects/<doc_id>/molecules/`
/// - Legacy: `molecules/<doc_slug>/`
fn molecule_output_dir(
    project_root: &Path,
    source_path: &Path,
    doc_slug: &str,
) -> Result<PathBuf, String> {
    let path = if let Some(doc_id) = document_project_id_from_source_path(project_root, source_path)
    {
        project_root
            .join(PROJECTS_DIR)
            .join(doc_id)
            .join(MOLECULES_DIR)
    } else {
        project_root.join(MOLECULES_DIR).join(doc_slug)
    };

    let root_str = project_root.to_string_lossy().to_string();
    assert_within_root_allow_missing(&root_str, &path)
}

/// If `source_path` is a DocumentProject source file
/// (`projects/<doc_id>/source.pdf`), return the `<doc_id>`.
fn document_project_id_from_source_path(
    project_root: &Path,
    source_path: &Path,
) -> Option<String> {
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn molecule_service_constructs_with_url() {
        let svc = MoleculeService::new("http://127.0.0.1:18792");
        assert_eq!(svc.sidecar_url, "http://127.0.0.1:18792");
    }

    #[test]
    fn detected_molecule_mapping_handles_negative_page() {
        let raw = DetectedMolecule {
            esmiles: "CCO".into(),
            confidence: 0.9,
            moldet_conf: 0.8,
            page: -3,
            crop_path: "/tmp/x.png".into(),
            bbox_pdf: [1.0, 2.0, 3.0, 4.0],
        };
        let res = into_detected_result(raw);
        assert_eq!(res.page, 0);
        assert_eq!(res.esmiles, "CCO");
    }
}
