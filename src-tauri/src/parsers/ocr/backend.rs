//! Unified OCR backend interface with per-page routing support.

use serde::{Deserialize, Serialize};

use crate::parsers::doc_types::{ImageRef, OcrBlock};

/// Output of an OCR backend.
#[derive(Debug, Clone, Serialize, Deserialize)]
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

/// Return all available backends in priority order.
pub fn available_backends() -> Vec<Box<dyn OcrBackend>> {
    vec![
        Box::new(crate::parsers::ocr::mineru::MineruBackend),
        Box::new(crate::parsers::ocr::uniparser::UniparserBackend),
        Box::new(crate::parsers::ocr::paddle::PaddleOnlineBackend),
        Box::new(crate::parsers::ocr::paddle::PaddleLocalBackend),
    ]
}

/// Filter OCR output down to selected page numbers.
///
/// This fallback keeps the full OCR text but restricts returned images and
/// OCR blocks to the requested pages. Backends that natively support page
/// ranges should override `run_pages` instead of relying on this fallback.
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

#[cfg(test)]
mod tests {
    use super::*;

    fn make_output(page_count: usize) -> OcrOutput {
        OcrOutput {
            text: "full text".to_string(),
            page_count,
            images: vec![
                ImageRef {
                    filename: "p1.png".to_string(),
                    page: 1,
                    region: None,
                    description: None,
                    esmiles: None,
                    rel_path: None,
                },
                ImageRef {
                    filename: "p2.png".to_string(),
                    page: 2,
                    region: None,
                    description: None,
                    esmiles: None,
                    rel_path: None,
                },
                ImageRef {
                    filename: "p3.png".to_string(),
                    page: 3,
                    region: None,
                    description: None,
                    esmiles: None,
                    rel_path: None,
                },
            ],
            ocr_blocks: vec![
                OcrBlock {
                    page: 1,
                    block_type: "text".to_string(),
                    bbox: [0.0; 4],
                    content: Some("block1".to_string()),
                    index: 0,
                    angle: 0,
                },
                OcrBlock {
                    page: 2,
                    block_type: "text".to_string(),
                    bbox: [0.0; 4],
                    content: Some("block2".to_string()),
                    index: 0,
                    angle: 0,
                },
                OcrBlock {
                    page: 3,
                    block_type: "text".to_string(),
                    bbox: [0.0; 4],
                    content: Some("block3".to_string()),
                    index: 0,
                    angle: 0,
                },
            ],
        }
    }

    #[test]
    fn test_filter_pages_empty_returns_all() {
        let out = make_output(3);
        let filtered = filter_pages(out, &[]);
        assert_eq!(filtered.images.len(), 3);
        assert_eq!(filtered.ocr_blocks.len(), 3);
    }

    #[test]
    fn test_filter_pages_selects_subset() {
        let out = make_output(3);
        let filtered = filter_pages(out, &[2]);
        assert_eq!(filtered.images.len(), 1);
        assert_eq!(filtered.images[0].page, 2);
        assert_eq!(filtered.ocr_blocks.len(), 1);
        assert_eq!(filtered.ocr_blocks[0].page, 2);
    }
}
