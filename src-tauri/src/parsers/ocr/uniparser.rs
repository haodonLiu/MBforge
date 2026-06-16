//! Uniparser online OCR backend.
//!
//! Online API: env var `UNIPARSER_API_KEY` (host `UNIPARSER_HOST`,
//! default `https://uniparser.dp.tech`). Auth: `X-API-Key` header.
//!
//! Flow (delegated to [`crate::parsers::pdf::uniparser::UniParserClient`]):
//! 1. POST multipart `/trigger-file-async` with `sync=true`.
//! 2. POST JSON `/get-formatted` and read `content` (markdown).

use super::OcrOutput;

pub fn is_available() -> bool {
    std::env::var("UNIPARSER_API_KEY")
        .map(|k| !k.trim().is_empty())
        .unwrap_or(false)
}

pub async fn run(pdf_path: &str) -> Result<OcrOutput, String> {
    let pdf_path_owned = pdf_path.to_owned();
    let inner = tokio::task::spawn_blocking(move || -> Result<(String, usize), String> {
        let host = std::env::var("UNIPARSER_HOST")
            .unwrap_or_else(|_| "https://uniparser.dp.tech".to_string());
        let api_key = std::env::var("UNIPARSER_API_KEY").unwrap_or_default();
        let client = crate::parsers::pdf::uniparser::UniParserClient::new(&host, &api_key);
        let r = client
            .parse_pdf(&pdf_path_owned)
            .map_err(|e| format!("Uniparser parse failed: {e}"))?;
        Ok((r.content, r.page_count))
    })
    .await
    .map_err(|e| format!("Uniparser task join error: {e}"))??;

    Ok(OcrOutput {
        text: inner.0,
        page_count: inner.1,
        ocr_blocks: vec![],
        images: vec![],
    })
}