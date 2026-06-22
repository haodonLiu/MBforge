//! OCR backend helpers for scanned PDFs.
//!
//! Each backend exposes a plain async `run` function returning
//! [`OcrOutput`]. The fallback chain in `classify_and_extract`
//! branches on env-var presence + backend availability before calling
//! each `run`.
//!
//! Scanned PDFs fall back to pdf-inspector text when no cloud OCR
//! backend is available.
//!
//! Status:
//! - MinerU: real impl in `parsers/pdf/mineru.rs` (re-exported here)
//! - Uniparser online: stub, returns `not_implemented`
//! - PaddleOCR online: stub, returns `not_implemented`
//! - PaddleOCR local: stub, returns `not_implemented`

use serde::Serialize;

pub mod backend;
pub mod paddle;
pub mod uniparser;

use crate::parsers::doc_types::ImageRef;

/// Re-export of MinerU's real implementation so `classify_and_extract`
/// can call into one consistent surface.
pub mod mineru {
    use super::{ImageRef, OcrOutput};

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

        let ocr_blocks = inner
            .ocr_blocks
            .into_iter()
            .map(serde_json::to_value)
            .collect::<Result<Vec<_>, _>>()
            .unwrap_or_default();
        let images: Vec<ImageRef> = inner.images;
        Ok(OcrOutput {
            text: inner.markdown,
            page_count: 0,
            ocr_blocks,
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
}

#[derive(Debug, Clone, Serialize)]
pub struct OcrOutput {
    pub text: String,
    pub page_count: usize,
    /// Backend-reported block layout (page, bbox, type, content).
    /// Empty when backend does not provide structured layout.
    pub ocr_blocks: Vec<serde_json::Value>,
    /// Backend-extracted images (figures, molecule renderings, etc.).
    /// Empty when backend does not return structured images. For MinerU
    /// these carry temp-dir paths until the caller persists them.
    pub images: Vec<ImageRef>,
}

