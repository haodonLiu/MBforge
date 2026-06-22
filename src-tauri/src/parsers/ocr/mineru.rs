//! MinerU cloud OCR backend.
//!
//! Real implementation is delegated to [`crate::parsers::pdf::mineru::MineruClient`].

use super::OcrOutput;
use crate::parsers::doc_types::ImageRef;

/// Run MinerU cloud OCR via [`MineruClient`].
/// Caller must check [`is_available`] first.
///
/// Implementation note: [`MineruClient::new`] builds a
/// `reqwest::blocking::Client`, which panics if constructed outside
/// a sync context. We therefore do ALL of: env reads, client build,
/// and HTTP call inside one `spawn_blocking` closure.
pub async fn run(pdf_path: &str) -> Result<OcrOutput, String> {
    let pdf_path_owned = pdf_path.to_owned();
    let inner = tokio::task::spawn_blocking(move || -> Result<RawMineru, String> {
        use crate::parsers::pdf::mineru::{MineruClient, MineruOptions};
        let host =
            std::env::var("MINERU_HOST").unwrap_or_else(|_| "https://mineru.net".to_string());
        let api_key = std::env::var("MINERU_API_KEY").unwrap_or_default();
        let client = MineruClient::new(&host, &api_key);
        let options = MineruOptions::scanned_for(&pdf_path_owned);
        let r = client
            .parse_file_with_options(&pdf_path_owned, &options)
            .map_err(|e| format!("MinerU OCR failed: {e}"))?;
        Ok(RawMineru {
            markdown: r.markdown,
            images: r.images,
            ocr_blocks: r.ocr_blocks,
        })
    })
    .await
    .map_err(|e| format!("MinerU task join error: {e}"))??;

    let images: Vec<ImageRef> = inner.images;
    Ok(OcrOutput {
        text: inner.markdown,
        page_count: 0,
        ocr_blocks: inner.ocr_blocks,
        images,
    })
}

pub fn is_available() -> bool {
    std::env::var("MINERU_API_KEY")
        .map(|k| !k.trim().is_empty())
        .unwrap_or(false)
}

struct RawMineru {
    markdown: String,
    images: Vec<ImageRef>,
    ocr_blocks: Vec<crate::parsers::doc_types::OcrBlock>,
}

// Trait extension so we can call `MineruOptions::scanned_for(path)`
// without repeating the field shape at every call site.
trait MineruOptionsExt {
    fn scanned_for(path: &str) -> crate::parsers::pdf::mineru::MineruOptions;
}

impl MineruOptionsExt for crate::parsers::pdf::mineru::MineruOptions {
    fn scanned_for(path: &str) -> crate::parsers::pdf::mineru::MineruOptions {
        crate::parsers::pdf::mineru::scanned_pdf_options(path)
    }
}

/// Trait wrapper for the MinerU OCR backend.
pub struct MineruBackend;

#[async_trait::async_trait]
impl crate::parsers::ocr::backend::OcrBackend for MineruBackend {
    fn name(&self) -> &'static str {
        "mineru"
    }

    fn is_available(&self) -> bool {
        is_available()
    }

    async fn run(&self, path: &str) -> Result<crate::parsers::ocr::backend::OcrOutput, String> {
        run(path).await
    }
}
