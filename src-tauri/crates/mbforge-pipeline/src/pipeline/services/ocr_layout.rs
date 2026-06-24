//! OCR layout service for pipeline v2.
//!
//! Exposes `get_ocr_layout`, a service-layer helper that returns the raw OCR
//! layout blocks (bounding boxes + text) for a PDF.  The returned block shape
//! mirrors the `OcrBlock` struct used by `commands/pdf.rs::get_document_ocr_layout`.

use std::path::Path;

use serde::{Deserialize, Serialize};

use crate::pipeline::context::PipelineContext;
use crate::pipeline::models::extracted::OcrBlock;
use crate::pipeline::services::ocr::{default_backends, OcrService};

/// A single OCR layout block.
///
/// Fields are kept identical to `crate::doc_types::OcrBlock` so that
/// frontend consumers of `get_document_ocr_layout` can reuse their parsing logic.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OcrLayoutBlock {
    /// Page number (1-based).
    pub page: usize,
    /// Block type, e.g. "text", "image", "table", "formula".
    pub block_type: String,
    /// Bounding box `[x1, y1, x2, y2]` in PDF coordinates.
    pub bbox: [f64; 4],
    /// Text content when `block_type` is text-like.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub content: Option<String>,
    /// Block index on the page.
    pub index: usize,
    /// Rotation angle (0/90/180/270).
    #[serde(default)]
    pub angle: i32,
}

impl From<OcrBlock> for OcrLayoutBlock {
    fn from(block: OcrBlock) -> Self {
        Self {
            page: block.page,
            block_type: block.block_type,
            bbox: block.bbox,
            content: block.content,
            index: block.index,
            angle: block.angle,
        }
    }
}

/// Extract OCR layout blocks for the given PDF.
///
/// Respects `ctx.config.allow_ocr`: when OCR is disabled, returns an empty
/// vector without invoking any backend.
///
/// # Errors
///
/// Returns a human-readable error string when no OCR backend can process the
/// document or when the path is not valid UTF-8.
pub async fn get_ocr_layout(
    path: &Path,
    ctx: &PipelineContext,
) -> Result<Vec<OcrLayoutBlock>, String> {
    if !ctx.config.allow_ocr {
        log::debug!("[ocr_layout] OCR disabled by context; returning empty layout");
        return Ok(Vec::new());
    }

    log::info!("[ocr_layout] running OCR for {}", path.display());

    let service = OcrService::new(default_backends());
    let (output, backend_name) = service.run(path).await.map_err(|e| e.to_string())?;

    log::info!(
        "[ocr_layout] backend '{}' produced {} blocks for {}",
        backend_name,
        output.ocr_blocks.len(),
        path.display()
    );

    Ok(output.ocr_blocks.into_iter().map(OcrLayoutBlock::from).collect())
}
