//! OCR service abstraction for the extract stage.
//!
//! This module defines the `OcrBackend` trait used by multiple OCR
//! implementations and a fallthrough `OcrService` that runs each available
//! backend in order until one succeeds.

use std::path::Path;

use async_trait::async_trait;

use crate::parsers::pipeline_v2::error::{ExtractError, PipelineError};
use crate::parsers::pipeline_v2::models::extracted::{ImageRef, OcrBlock};

/// Output produced by a single OCR backend.
#[derive(Debug, Clone)]
pub struct OcrOutput {
    /// Full text recognized across all pages, in reading order.
    pub text: String,

    /// Total number of pages processed.
    pub page_count: usize,

    /// Images extracted during OCR, typically figure or scheme crops.
    pub images: Vec<ImageRef>,

    /// Per-block OCR geometry and classification.
    pub ocr_blocks: Vec<OcrBlock>,
}

/// Pluggable backend that performs OCR on a PDF file.
#[async_trait]
pub trait OcrBackend: Send + Sync {
    /// Unique backend identifier used for diagnostics and routing.
    fn name(&self) -> &'static str;

    /// Whether this backend is configured and ready to run.
    fn is_available(&self) -> bool;

    /// Run OCR on the PDF at `path`.
    ///
    /// # Errors
    ///
    /// Returns a `PipelineError` when the backend cannot process the file.
    async fn run(&self, path: &Path) -> Result<OcrOutput, PipelineError>;
}

/// Service that tries configured OCR backends until one succeeds.
pub struct OcrService {
    backends: Vec<Box<dyn OcrBackend>>,
}

impl OcrService {
    /// Create a new OCR service with the given ordered list of backends.
    pub fn new(backends: Vec<Box<dyn OcrBackend>>) -> Self {
        Self { backends }
    }

    /// Run the first available OCR backend against `path`.
    ///
    /// Backends are tried in registration order. The name of the successful
    /// backend is returned alongside its output so callers can record which
    /// parser produced the result.
    ///
    /// # Errors
    ///
    /// Returns `PipelineError::Extract(ExtractError::OcrAllBackendsFailed)`
    /// when every available backend fails, or when no backend is available.
    pub async fn run(&self, path: &Path) -> Result<(OcrOutput, &'static str), PipelineError> {
        let path_str = path.to_string_lossy().to_string();
        let mut errors = Vec::new();

        for backend in &self.backends {
            if !backend.is_available() {
                continue;
            }
            match backend.run(path).await {
                Ok(out) => return Ok((out, backend.name())),
                Err(e) => errors.push(format!("{}: {}", backend.name(), e)),
            }
        }

        Err(PipelineError::Extract(ExtractError::OcrAllBackendsFailed {
            path: path_str,
            details: errors.join("; "),
        }))
    }
}

// ---------------------------------------------------------------------------
// Conversion helpers from legacy OCR types to pipeline_v2 OCR types.
// ---------------------------------------------------------------------------

/// Convert a legacy `doc_types::ImageRef` into the pipeline_v2 equivalent.
fn adapt_image_ref(old: &crate::parsers::doc_types::ImageRef) -> ImageRef {
    ImageRef {
        filename: old.filename.clone(),
        page: old.page,
        region: old.region.clone(),
        description: old.description.clone(),
        esmiles: old.esmiles.clone(),
        rel_path: old.rel_path.clone(),
    }
}

/// Convert a legacy `doc_types::OcrBlock` into the pipeline_v2 equivalent.
fn adapt_ocr_block(old: &crate::parsers::doc_types::OcrBlock) -> OcrBlock {
    OcrBlock {
        page: old.page,
        block_type: old.block_type.clone(),
        bbox: old.bbox,
        content: old.content.clone(),
        index: old.index,
        angle: old.angle,
    }
}

/// Convert a legacy OCR backend output into the pipeline_v2 `OcrOutput`.
fn adapt_ocr_output(old: crate::parsers::ocr::OcrOutput) -> OcrOutput {
    OcrOutput {
        text: old.text,
        page_count: old.page_count,
        images: old.images.iter().map(adapt_image_ref).collect(),
        ocr_blocks: old.ocr_blocks.iter().map(adapt_ocr_block).collect(),
    }
}

// ---------------------------------------------------------------------------
// Backend adapters wiring legacy OCR free functions into the new trait.
// ---------------------------------------------------------------------------

/// Adapter wiring the MinerU cloud OCR backend into the new pipeline.
pub struct MineruBackendAdapter;

#[async_trait]
impl OcrBackend for MineruBackendAdapter {
    fn name(&self) -> &'static str {
        "mineru"
    }

    fn is_available(&self) -> bool {
        crate::parsers::ocr::mineru::is_available()
    }

    async fn run(&self, path: &Path) -> Result<OcrOutput, PipelineError> {
        match crate::parsers::ocr::mineru::run(path.to_string_lossy().as_ref()).await {
            Ok(out) => Ok(adapt_ocr_output(out)),
            Err(e) => Err(PipelineError::Extract(ExtractError::InspectorFailed {
                path: path.to_string_lossy().to_string(),
                detail: e,
            })),
        }
    }
}

/// Adapter wiring the UniParser online OCR backend into the new pipeline.
pub struct UniparserBackendAdapter;

#[async_trait]
impl OcrBackend for UniparserBackendAdapter {
    fn name(&self) -> &'static str {
        "uniparser"
    }

    fn is_available(&self) -> bool {
        crate::parsers::ocr::uniparser::is_available()
    }

    async fn run(&self, path: &Path) -> Result<OcrOutput, PipelineError> {
        match crate::parsers::ocr::uniparser::run(path.to_string_lossy().as_ref()).await {
            Ok(out) => Ok(adapt_ocr_output(out)),
            Err(e) => Err(PipelineError::Extract(ExtractError::InspectorFailed {
                path: path.to_string_lossy().to_string(),
                detail: e,
            })),
        }
    }
}

/// Adapter wiring the PaddleOCR online backend into the new pipeline.
pub struct PaddleBackendAdapter;

#[async_trait]
impl OcrBackend for PaddleBackendAdapter {
    fn name(&self) -> &'static str {
        "paddleocr-online"
    }

    fn is_available(&self) -> bool {
        crate::parsers::ocr::paddle::online_is_available()
    }

    async fn run(&self, path: &Path) -> Result<OcrOutput, PipelineError> {
        match crate::parsers::ocr::paddle::run_online(path.to_string_lossy().as_ref()).await {
            Ok(out) => Ok(adapt_ocr_output(out)),
            Err(e) => Err(PipelineError::Extract(ExtractError::InspectorFailed {
                path: path.to_string_lossy().to_string(),
                detail: e,
            })),
        }
    }
}

/// Placeholder adapter for the GLM-OCR backend.
pub struct GlmOcrBackendAdapter;

#[async_trait]
impl OcrBackend for GlmOcrBackendAdapter {
    fn name(&self) -> &'static str {
        "glm-ocr"
    }

    fn is_available(&self) -> bool {
        false
    }

    async fn run(&self, path: &Path) -> Result<OcrOutput, PipelineError> {
        Err(PipelineError::Extract(ExtractError::InspectorFailed {
            path: path.to_string_lossy().to_string(),
            detail: "glm-ocr backend not implemented".to_string(),
        }))
    }
}

/// Placeholder adapter for the GLM-4.6V-Flash backend.
pub struct Glm4VBackendAdapter;

#[async_trait]
impl OcrBackend for Glm4VBackendAdapter {
    fn name(&self) -> &'static str {
        "glm-4.6v-flash"
    }

    fn is_available(&self) -> bool {
        false
    }

    async fn run(&self, path: &Path) -> Result<OcrOutput, PipelineError> {
        Err(PipelineError::Extract(ExtractError::InspectorFailed {
            path: path.to_string_lossy().to_string(),
            detail: "glm-4.6v-flash backend not implemented".to_string(),
        }))
    }
}

/// Returns the default ordered list of OCR backends.
pub fn default_backends() -> Vec<Box<dyn OcrBackend>> {
    vec![
        Box::new(MineruBackendAdapter),
        Box::new(UniparserBackendAdapter),
        Box::new(PaddleBackendAdapter),
        Box::new(GlmOcrBackendAdapter),
        Box::new(Glm4VBackendAdapter),
    ]
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn adapt_ocr_output_copies_all_fields() {
        let old = crate::parsers::ocr::backend::OcrOutput {
            text: "sample text".to_string(),
            page_count: 2,
            images: vec![crate::parsers::doc_types::ImageRef {
                filename: "img.png".to_string(),
                page: 1,
                region: Some("region-a".to_string()),
                description: Some("desc".to_string()),
                esmiles: Some("CCO".to_string()),
                rel_path: Some("media/img.png".to_string()),
            }],
            ocr_blocks: vec![crate::parsers::doc_types::OcrBlock {
                page: 1,
                block_type: "text".to_string(),
                bbox: [1.0, 2.0, 3.0, 4.0],
                content: Some("block content".to_string()),
                index: 7,
                angle: 90,
            }],
        };

        let new = adapt_ocr_output(old);

        assert_eq!(new.text, "sample text");
        assert_eq!(new.page_count, 2);
        assert_eq!(new.images.len(), 1);
        let img = &new.images[0];
        assert_eq!(img.filename, "img.png");
        assert_eq!(img.page, 1);
        assert_eq!(img.region.as_deref(), Some("region-a"));
        assert_eq!(img.description.as_deref(), Some("desc"));
        assert_eq!(img.esmiles.as_deref(), Some("CCO"));
        assert_eq!(img.rel_path.as_deref(), Some("media/img.png"));
        assert_eq!(new.ocr_blocks.len(), 1);
        let block = &new.ocr_blocks[0];
        assert_eq!(block.page, 1);
        assert_eq!(block.block_type, "text");
        assert_eq!(block.bbox, [1.0, 2.0, 3.0, 4.0]);
        assert_eq!(block.content.as_deref(), Some("block content"));
        assert_eq!(block.index, 7);
        assert_eq!(block.angle, 90);
    }

    #[test]
    fn stub_glm_adapters_are_unavailable() {
        assert!(!GlmOcrBackendAdapter.is_available());
        assert!(!Glm4VBackendAdapter.is_available());
    }
}
