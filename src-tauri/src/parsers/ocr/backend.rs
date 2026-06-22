//! Unified OCR backend interface with per-page routing support.

use crate::parsers::doc_types::{ImageRef, OcrBlock};

/// Output of an OCR backend.
#[derive(Debug, Clone)]
pub struct OcrOutput {
    pub text: String,
    pub page_count: usize,
    pub images: Vec<ImageRef>,
    pub ocr_blocks: Vec<OcrBlock>,
}

/// Per-page OCR backend abstraction.
#[async_trait::async_trait]
pub trait OcrBackend: Send + Sync {
    fn name(&self) -> &'static str;
    fn is_available(&self) -> bool;

    /// Run OCR on the entire document.
    async fn run(&self, path: &str) -> Result<OcrOutput, String>;

    /// Run OCR on selected pages. Default implementation runs the whole
    /// document and then filters to the requested pages.
    async fn run_pages(&self, path: &str, pages: &[usize]) -> Result<OcrOutput, String> {
        let full = self.run(path).await?;
        Ok(filter_pages(full, pages))
    }
}

/// Filter OCR output down to selected page numbers.
///
/// Backends that natively support page ranges should override `run_pages`
/// instead of relying on this fallback.
pub fn filter_pages(output: OcrOutput, pages: &[usize]) -> OcrOutput {
    if pages.is_empty() {
        return output;
    }
    let page_set: std::collections::HashSet<usize> = pages.iter().copied().collect();
    let images = output
        .images
        .into_iter()
        .filter(|img| page_set.contains(&(img.page as usize)))
        .collect();
    let ocr_blocks = output
        .ocr_blocks
        .into_iter()
        .filter(|b| page_set.contains(&(b.page as usize)))
        .collect();
    OcrOutput {
        text: output.text,
        page_count: output.page_count,
        images,
        ocr_blocks,
    }
}
