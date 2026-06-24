use serde::{Deserialize, Serialize};

/// UniParser API client — pure Rust, no Python dependency.
///
/// API: https://uniparser.dp.tech/
/// Auth: X-API-Key header
pub struct UniParserClient {
    host: String,
    api_key: String,
    client: reqwest::blocking::Client,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct UniParserResult {
    pub content: String,
    pub page_count: usize,
    pub token: String,
    pub source: String,
}

impl UniParserClient {
    pub fn new(host: &str, api_key: &str) -> Self {
        let client = reqwest::blocking::Client::builder()
            .timeout(std::time::Duration::from_secs(300))
            .build()
            .expect("Failed to create HTTP client");

        Self {
            host: host.trim_end_matches('/').to_string(),
            api_key: api_key.to_string(),
            client,
        }
    }

    /// Parse a PDF file via UniParser API.
    ///
    /// 1. Upload PDF → get token
    /// 2. Get formatted result with token
    pub fn parse_pdf(&self, pdf_path: &str) -> Result<UniParserResult, String> {
        let path = std::path::Path::new(pdf_path);
        if !path.exists() {
            return Err(format!("File not found: {}", pdf_path));
        }

        let pdf_bytes = std::fs::read(path).map_err(|e| format!("Failed to read PDF: {}", e))?;
        let filename = path
            .file_name()
            .and_then(|n| n.to_str())
            .unwrap_or("document.pdf");

        // Step 1: Upload and trigger parsing
        let token = self.trigger_file(pdf_bytes, filename)?;

        // Step 2: Get formatted result (sync, wait for completion)
        self.get_formatted(&token)
    }

    /// Upload PDF and trigger async parsing.
    fn trigger_file(&self, pdf_bytes: Vec<u8>, filename: &str) -> Result<String, String> {
        let url = format!("{}/trigger-file-async", self.host);
        let token = format!("mbforge_{}", uuid::Uuid::new_v4());

        let form = reqwest::blocking::multipart::Form::new()
            .text("token", token.clone())
            .text("sync", "true")
            .text("textual", "2") // high quality
            .text("table", "2") // high quality
            .text("equation", "2") // high quality
            .text("molecule", "1") // fast
            .part(
                "file",
                reqwest::blocking::multipart::Part::bytes(pdf_bytes)
                    .file_name(filename.to_string())
                    .mime_str("application/pdf")
                    .map_err(|e| format!("MIME error: {}", e))?,
            );

        let resp = self
            .client
            .post(&url)
            .header("X-API-Key", &self.api_key)
            .multipart(form)
            .send()
            .map_err(|e| format!("UniParser trigger failed: {}", e))?;

        if !resp.status().is_success() {
            let status = resp.status();
            let body = resp.text().unwrap_or_default();
            return Err(format!("UniParser HTTP {}: {}", status, body));
        }

        let _: serde_json::Value = resp
            .json()
            .map_err(|e| format!("UniParser trigger response error: {}", e))?;

        Ok(token)
    }

    /// Get formatted result with Markdown output.
    fn get_formatted(&self, token: &str) -> Result<UniParserResult, String> {
        let url = format!("{}/get-formatted", self.host);

        let body = serde_json::json!({
            "token": token,
            "content": true,
            "textual": "markdown",
            "table": "markdown",
            "equation": "markdown",
        });

        let resp = self
            .client
            .post(&url)
            .header("X-API-Key", &self.api_key)
            .header("Content-Type", "application/json")
            .json(&body)
            .send()
            .map_err(|e| format!("UniParser get-formatted failed: {}", e))?;

        if !resp.status().is_success() {
            let status = resp.status();
            let body = resp.text().unwrap_or_default();
            return Err(format!("UniParser HTTP {}: {}", status, body));
        }

        let result: serde_json::Value = resp
            .json()
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
        let client = UniParserClient::new("https://example.com/", "test_key");
        assert_eq!(client.host, "https://example.com");
        assert_eq!(client.api_key, "test_key");
    }
}
