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
