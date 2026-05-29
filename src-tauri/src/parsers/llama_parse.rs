use serde::{Deserialize, Serialize};

/// LlamaParse API response for parsed document.
#[derive(Debug, Deserialize)]
pub struct LlamaParseResponse {
    pub pages: Option<Vec<LlamaParsePage>>,
    pub markdown: Option<String>,
    pub error: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct LlamaParsePage {
    pub page: u32,
    pub text: Option<String>,
    pub markdown: Option<String>,
}

#[derive(Debug, Serialize)]
pub struct LlamaParseResult {
    pub markdown: String,
    pub page_count: usize,
    pub source: String,
}

/// Call LlamaParse API to parse a PDF file.
///
/// `api_url` — LlamaParse server URL (e.g., "http://localhost:8000")
/// `pdf_bytes` — raw PDF file bytes
/// `api_key` — optional API key for cloud LlamaParse
pub async fn parse_with_llamaparse(
    api_url: &str,
    pdf_bytes: Vec<u8>,
    api_key: Option<&str>,
) -> Result<LlamaParseResult, String> {
    let client = reqwest::Client::new();
    let url = format!("{}/v1/file/upload", api_url.trim_end_matches('/'));

    let mut form = reqwest::multipart::Form::new()
        .part("file", reqwest::multipart::Part::bytes(pdf_bytes)
            .file_name("document.pdf")
            .mime_str("application/pdf")
            .map_err(|e| format!("MIME error: {}", e))?)
        .text("result_type", "markdown");

    if let Some(key) = api_key {
        if !key.is_empty() {
            form = form.text("api_key", key);
        }
    }

    let resp = client.post(&url)
        .multipart(form)
        .timeout(std::time::Duration::from_secs(120))
        .send()
        .await
        .map_err(|e| format!("LlamaParse request failed: {}", e))?;

    if !resp.status().is_success() {
        let status = resp.status();
        let body = resp.text().await.unwrap_or_default();
        return Err(format!("LlamaParse HTTP {}: {}", status, body));
    }

    let parsed: LlamaParseResponse = resp.json().await
        .map_err(|e| format!("LlamaParse response parse error: {}", e))?;

    if let Some(err) = parsed.error {
        return Err(format!("LlamaParse error: {}", err));
    }

    let markdown = parsed.markdown.unwrap_or_default();
    let page_count = parsed.pages.as_ref().map_or(0, |p| p.len());

    Ok(LlamaParseResult {
        markdown,
        page_count,
        source: "llama_parse".to_string(),
    })
}

/// Call LlamaParse API synchronously (blocking wrapper for non-async contexts).
pub fn parse_with_llamaparse_sync(
    api_url: &str,
    pdf_bytes: Vec<u8>,
    api_key: Option<&str>,
) -> Result<LlamaParseResult, String> {
    let rt = tokio::runtime::Runtime::new()
        .map_err(|e| format!("Failed to create tokio runtime: {}", e))?;
    rt.block_on(parse_with_llamaparse(api_url, pdf_bytes, api_key))
}
