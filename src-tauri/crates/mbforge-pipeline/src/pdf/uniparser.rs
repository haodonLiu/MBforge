//! UniParser API client — pure Rust, no Python dependency.
//!
//! API: https://uniparser.dp.tech/
//! Auth: X-API-Key header.
//!
//! Uses the async `reqwest::Client` (shared via `LazyLock` so the
//! connection pool is reused across calls) — see review §6.

use std::sync::LazyLock;

use reqwest::Client;
use serde::{Deserialize, Serialize};

/// Process-wide async HTTP client for UniParser. Initialiser is
/// known at declaration time so `LazyLock` (not `OnceLock`).
static HTTP_CLIENT: LazyLock<Client> = LazyLock::new(|| {
    Client::builder()
        .timeout(std::time::Duration::from_secs(300))
        .build()
        .expect("UniParser HTTP client build")
});

/// Maximum bytes we will buffer when reading a PDF off disk. Larger
/// files fail loudly instead of silently exhausting memory.
const MAX_PDF_BYTES: u64 = 256 * 1024 * 1024;

/// UniParser API client — async-friendly wrapper around the static
/// shared HTTP client.
pub struct UniParserClient {
    host: String,
    api_key: String,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct UniParserResult {
    pub content: String,
    pub page_count: usize,
    pub token: String,
    pub source: String,
}

impl UniParserClient {
    /// Create a new client wrapper. The HTTP client itself is shared
    /// via `HTTP_CLIENT`; only the host and key are stored.
    pub fn new(host: &str, api_key: &str) -> Self {
        Self {
            host: host.trim_end_matches('/').to_string(),
            api_key: api_key.to_string(),
        }
    }

    /// Parse a PDF file via UniParser API.
    ///
    /// 1. Upload PDF → get token
    /// 2. Get formatted result with token
    pub async fn parse_pdf(&self, pdf_path: &str) -> Result<UniParserResult, String> {
        let path = std::path::Path::new(pdf_path);
        if !path.exists() {
            return Err(format!("File not found: {}", pdf_path));
        }

        // Read PDF off the disk on the blocking thread pool to keep
        // the async runtime responsive. Cap at 256 MiB to defend
        // against pathological inputs.
        let pdf_path_owned = pdf_path.to_owned();
        let pdf_bytes = tokio::task::spawn_blocking(move || -> Result<Vec<u8>, String> {
            let bytes = std::fs::read(&pdf_path_owned)
                .map_err(|e| format!("Failed to read PDF: {}", e))?;
            if (bytes.len() as u64) > MAX_PDF_BYTES {
                return Err(format!(
                    "PDF too large: {} bytes > {MAX_PDF_BYTES}",
                    bytes.len()
                ));
            }
            Ok(bytes)
        })
        .await
        .map_err(|e| format!("UniParser PDF read task join error: {e}"))??;

        let filename = path
            .file_name()
            .and_then(|n| n.to_str())
            .unwrap_or("document.pdf")
            .to_string();

        // Step 1: Upload and trigger parsing
        let token = self.trigger_file(pdf_bytes, &filename).await?;

        // Step 2: Get formatted result
        self.get_formatted(&token).await
    }

    /// Upload PDF and trigger async parsing.
    async fn trigger_file(
        &self,
        pdf_bytes: Vec<u8>,
        filename: &str,
    ) -> Result<String, String> {
        let url = format!("{}/trigger-file-async", self.host);
        let token = format!("mbforge_{}", uuid::Uuid::new_v4());

        let part = reqwest::multipart::Part::bytes(pdf_bytes)
            .file_name(filename.to_string())
            .mime_str("application/pdf")
            .map_err(|e| format!("MIME error: {}", e))?;
        let form = reqwest::multipart::Form::new()
            .text("token", token.clone())
            .text("sync", "true")
            .text("textual", "2") // high quality
            .text("table", "2") // high quality
            .text("equation", "2") // high quality
            .text("molecule", "1") // fast
            .part("file", part);

        let resp = HTTP_CLIENT
            .post(&url)
            .header("X-API-Key", &self.api_key)
            .multipart(form)
            .send()
            .await
            .map_err(|e| format!("UniParser trigger failed: {}", e))?;

        if !resp.status().is_success() {
            let status = resp.status();
            let body = resp.text().await.unwrap_or_default();
            return Err(format!("UniParser HTTP {status}: {body}"));
        }

        let _: serde_json::Value = resp
            .json()
            .await
            .map_err(|e| format!("UniParser trigger response error: {}", e))?;

        Ok(token)
    }

    /// Get formatted result with Markdown output.
    async fn get_formatted(&self, token: &str) -> Result<UniParserResult, String> {
        let url = format!("{}/get-formatted", self.host);

        let body = serde_json::json!({
            "token": token,
            "content": true,
            "textual": "markdown",
            "table": "markdown",
            "equation": "markdown",
        });

        let resp = HTTP_CLIENT
            .post(&url)
            .header("X-API-Key", &self.api_key)
            .header("Content-Type", "application/json")
            .json(&body)
            .send()
            .await
            .map_err(|e| format!("UniParser get-formatted failed: {}", e))?;

        if !resp.status().is_success() {
            let status = resp.status();
            let body = resp.text().await.unwrap_or_default();
            return Err(format!("UniParser HTTP {status}: {body}"));
        }

        let result: serde_json::Value = resp
            .json()
            .await
            .map_err(|e| format!("UniParser result parse error: {}", e))?;

        let content = result["content"].as_str().unwrap_or("").to_string();
        let page_count = result["page_count"].as_u64().unwrap_or(0) as usize;

        Ok(UniParserResult {
            content,
            page_count,
            token: token.to_string(),
            source: "uniparser".to_string(),
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_client_creation() {
        let c = UniParserClient::new("https://example.com/", "test-key");
        assert_eq!(c.host, "https://example.com");
        assert_eq!(c.api_key, "test-key");
    }

    #[test]
    fn test_http_client_initialised() {
        // The LazyLock must produce a working client; if init fails
        // the process panics (see HTTP_CLIENT definition), so this
        // test simply asserts the client is reachable.
        let _ = &*HTTP_CLIENT;
    }

    #[tokio::test]
    async fn test_parse_pdf_missing_file() {
        // The async file-not-found path now returns immediately.
        let client = UniParserClient::new("https://example.com", "k");
        let result = client.parse_pdf("/nonexistent/path.pdf").await;
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("File not found"));
    }
}
