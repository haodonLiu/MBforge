//! PDF page rendering via the Python sidecar (PyMuPDF).
//!
//! Renders PDF pages as images for MoldDet on text-based PDFs.

use base64::Engine;
use serde::{Deserialize, Serialize};

/// One rendered PDF page returned by the sidecar.
#[derive(Debug, Clone)]
pub struct RenderedPage {
    pub page_num: u32,
    pub width: u32,
    pub height: u32,
    pub image_bytes: Vec<u8>,
}

#[derive(Debug, Serialize)]
struct RenderPagesRequest {
    pdf_path: String,
    page_numbers: Vec<u32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    dpi: Option<f64>,
}

#[derive(Debug, Deserialize)]
struct ScreenshotDto {
    page_num: u32,
    width: u32,
    height: u32,
    image_base64: String,
}

#[derive(Debug, Deserialize)]
struct RenderPagesResponse {
    screenshots: Vec<ScreenshotDto>,
    count: usize,
}

/// Render a batch of PDF pages to PNG images using the Python sidecar.
///
/// `page_numbers` are 1-based.
/// Default DPI is 300.
pub async fn render_pages(
    pdf_path: &str,
    page_numbers: &[u32],
    sidecar_url: &str,
) -> Result<Vec<RenderedPage>, String> {
    if page_numbers.is_empty() {
        return Ok(vec![]);
    }
    // Cap the page count to prevent accidental DoS on a 10k-page PDF.
    const MAX_PAGES: usize = 256;
    if page_numbers.len() > MAX_PAGES {
        return Err(format!(
            "Too many pages requested ({} > {}); narrow the page_numbers range",
            page_numbers.len(),
            MAX_PAGES
        ));
    }

    let url = format!("{}/api/v1/pdf/render-pages", sidecar_url);
    let body = RenderPagesRequest {
        pdf_path: pdf_path.to_string(),
        page_numbers: page_numbers.to_vec(),
        dpi: Some(300.0),
    };

    // Use the shared connection pool instead of building a new client
    // per call.
    let client = mbforge_infra::http::client_120s();

    let resp = client
        .post(&url)
        .json(&body)
        .send()
        .await
        .map_err(|e| {
            if e.is_connect() || e.is_timeout() {
                format!(
                    "无法连接到 Python sidecar ({})。请确认模型服务器已启动：uv run uvicorn mbforge.server:app --host 127.0.0.1 --port 18792",
                    url
                )
            } else {
                format!("Sidecar render request failed: {}", e)
            }
        })?;

    if !resp.status().is_success() {
        let status = resp.status();
        let text = resp.text().await.unwrap_or_default();
        return Err(format!("sidecar render HTTP {} — {}", status, text));
    }

    let parsed: RenderPagesResponse = resp
        .json()
        .await
        .map_err(|e| format!("Sidecar render JSON parse failed: {}", e))?;

    let mut pages = Vec::with_capacity(parsed.count);
    for dto in parsed.screenshots {
        let image_bytes = base64::engine::general_purpose::STANDARD
            .decode(&dto.image_base64)
            .map_err(|e| format!("Failed to decode rendered page {}: {}", dto.page_num, e))?;
        pages.push(RenderedPage {
            page_num: dto.page_num,
            width: dto.width,
            height: dto.height,
            image_bytes,
        });
    }

    Ok(pages)
}
