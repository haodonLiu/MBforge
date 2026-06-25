//! Uniparser online OCR backend.
//!
//! Online API: env var `UNIPARSER_API_KEY` (host `UNIPARSER_HOST`,
//! default `https://uniparser.dp.tech`). Auth: `X-API-Key` header.
//!
//! Flow (delegated to [`crate::pdf::uniparser::UniParserClient`]):
//! 1. POST multipart `/trigger-file-async` with `sync=true`.
//! 2. POST JSON `/get-formatted` and read `content` (markdown).
//!
//! The PDF read happens inside the client via `tokio::task::spawn_blocking`
//! to keep the async runtime responsive; the actual HTTP calls are
//! fully async. Connection pool is shared via a `LazyLock` — see
//! review §6.

use super::OcrOutput;
use crate::pdf::uniparser::UniParserClient;

pub fn is_available() -> bool {
    std::env::var("UNIPARSER_API_KEY")
        .map(|k| !k.trim().is_empty())
        .unwrap_or(false)
}

pub async fn run(pdf_path: &str) -> Result<OcrOutput, String> {
    let host = std::env::var("UNIPARSER_HOST")
        .unwrap_or_else(|_| "https://uniparser.dp.tech".to_string());
    let api_key = std::env::var("UNIPARSER_API_KEY").unwrap_or_default();
    if api_key.trim().is_empty() {
        return Err("UNIPARSER_API_KEY is not set".to_string());
    }
    let client = UniParserClient::new(&host, &api_key);
    let r = client
        .parse_pdf(pdf_path)
        .await
        .map_err(|e| format!("Uniparser parse failed: {e}"))?;
    Ok(OcrOutput {
        text: r.content,
        page_count: r.page_count,
        ocr_blocks: vec![],
        images: vec![],
    })
}

/// Trait wrapper for the Uniparser OCR backend.
pub struct UniparserBackend;

#[async_trait::async_trait]
impl crate::ocr::backend::OcrBackend for UniparserBackend {
    fn name(&self) -> &'static str {
        "uniparser"
    }

    fn is_available(&self) -> bool {
        is_available()
    }

    async fn run(&self, path: &str) -> Result<crate::ocr::backend::OcrOutput, String> {
        run(path).await
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_is_available_false_when_key_empty() {
        let prev = std::env::var("UNIPARSER_API_KEY").ok();
        // SAFETY: test-only single-thread setup.
        unsafe {
            std::env::set_var("UNIPARSER_API_KEY", "");
        }
        assert!(!is_available());
        unsafe {
            std::env::set_var("UNIPARSER_API_KEY", "real-key");
        }
        assert!(is_available());
        match prev {
            Some(v) => unsafe { std::env::set_var("UNIPARSER_API_KEY", v) },
            None => unsafe { std::env::remove_var("UNIPARSER_API_KEY") },
        }
    }

    #[tokio::test]
    async fn test_run_missing_key_fails_fast() {
        let prev = std::env::var("UNIPARSER_API_KEY").ok();
        unsafe {
            std::env::remove_var("UNIPARSER_API_KEY");
        }
        let result = run("dummy.pdf").await;
        assert!(result.is_err());
        let err = result.unwrap_err();
        assert!(
            err.contains("UNIPARSER_API_KEY is not set"),
            "expected fast-fail error, got {err:?}"
        );
        match prev {
            Some(v) => unsafe { std::env::set_var("UNIPARSER_API_KEY", v) },
            None => unsafe { std::env::remove_var("UNIPARSER_API_KEY") },
        }
    }
}
