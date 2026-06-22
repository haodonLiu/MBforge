//! Molecule extraction service for the PDF processing pipeline.
//!
//! This service wraps [`extract_molecules_from_pdf`] and maps the raw
//! [`DetectedMolecule`] results into the pipeline-v2 [`DetectedMoleculeResult`]
//! model. It is used by the enrichment stage to identify chemical structures
//! embedded in PDF pages.

use std::path::Path;

use crate::parsers::doc_types::{ImageRef as DocImageRef, OcrBlock as DocOcrBlock};
use crate::parsers::pipeline::{extract_molecules_from_pdf, ClassifyResult};
use crate::parsers::pipeline_v2::error::{EnrichError, PipelineError};
use crate::parsers::pipeline_v2::models::enriched::DetectedMoleculeResult;
use crate::parsers::pipeline_v2::models::extracted::ExtractedDocument;

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
    /// the caller; it is forwarded to the molecule extraction backend which
    /// performs its own path handling.
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
        let classified = ClassifyResult {
            text: extracted.raw_text.clone(),
            page_count: extracted.page_count,
            parser: extracted.parser.clone(),
            images: extracted
                .images
                .iter()
                .map(|img| DocImageRef {
                    filename: img.filename.clone(),
                    page: img.page,
                    region: img.region.clone(),
                    description: img.description.clone(),
                    esmiles: img.esmiles.clone(),
                    rel_path: img.rel_path.clone(),
                })
                .collect(),
            ocr_blocks: extracted
                .ocr_blocks
                .iter()
                .map(|block| DocOcrBlock {
                    page: block.page,
                    block_type: block.block_type.clone(),
                    bbox: block.bbox,
                    content: block.content.clone(),
                    index: block.index,
                    angle: block.angle,
                })
                .collect(),
        };

        let detected =
            extract_molecules_from_pdf(path, &classified, &self.sidecar_url, project_root)
                .await
                .map_err(|e| {
                    PipelineError::Enrich(EnrichError::MoleculeServiceFailed { detail: e })
                })?;

        Ok(detected
            .into_iter()
            .map(|m| DetectedMoleculeResult {
                esmiles: m.esmiles,
                confidence: m.confidence,
                moldet_conf: m.moldet_conf,
                page: m.page.max(0) as usize,
                crop_path: m.crop_path,
                bbox_pdf: m.bbox_pdf,
            })
            .collect())
    }
}
