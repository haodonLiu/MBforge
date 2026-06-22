//! PDF inspector service for the extract stage.
//!
//! `InspectorService` wraps the low-level `PdfInspectorContext` loader and
//! converts its output into the canonical `ExtractedDocument` used by the
//! rest of the pipeline.

use std::path::Path;

use crate::parsers::pdf::context::PdfInspectorContext;
use crate::parsers::pipeline_v2::error::{ExtractError, PipelineError};
use crate::parsers::pipeline_v2::models::extracted::{ExtractedDocument, ExtractedMetadata};

/// Service that extracts raw text and metadata from a PDF file.
pub struct InspectorService;

impl InspectorService {
    /// Create a new inspector service instance.
    pub fn new() -> Self {
        Self
    }

    /// Extract text, page count and title from the PDF at `path`.
    ///
    /// Returns an `ExtractedDocument` populated from the pdf-inspector
    /// context. Images and OCR blocks are left empty because this service
    /// only performs native PDF text extraction.
    ///
    /// # Errors
    ///
    /// Returns `PipelineError::Extract(ExtractError::InspectorFailed)` when
    /// the underlying pdf-inspector loader fails.
    pub async fn extract(&self, path: &Path) -> Result<ExtractedDocument, PipelineError> {
        let path_str = path.to_string_lossy().to_string();

        let ctx = PdfInspectorContext::from_path(&path_str)
            .await
            .map_err(|e| {
                PipelineError::Extract(ExtractError::InspectorFailed {
                    path: path_str,
                    detail: e,
                })
            })?;

        Ok(ExtractedDocument {
            raw_text: ctx.markdown,
            page_count: ctx.page_count,
            parser: "pdf_inspector".into(),
            images: Vec::new(),
            ocr_blocks: Vec::new(),
            metadata: ExtractedMetadata {
                title: ctx.classification.title,
                ..ExtractedMetadata::default()
            },
        })
    }
}

impl Default for InspectorService {
    fn default() -> Self {
        Self::new()
    }
}
