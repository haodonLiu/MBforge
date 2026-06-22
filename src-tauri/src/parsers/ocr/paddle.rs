//! PaddleOCR backend — `online` is a real impl (Baidu AIStudio
//! `https://paddleocr.aistudio-app.com/api/v2/ocr/jobs`),
//! `local` is still a stub.
//!
//! Online flow:
//! 1. POST `/api/v2/ocr/jobs` with bearer token.
//!    - URL mode: JSON body `{ fileUrl, model, optionalPayload }`
//!    - Local mode: multipart `{ model, optionalPayload, file }`
//! 2. Poll `GET /api/v2/ocr/jobs/{jobId}` every 5s until `done` /
//!    `failed`.
//! 3. On `done`, GET `data.resultUrl.jsonUrl` (JSONL: one layout per
//!    page), parse, collect markdown text + image URLs.
//! 4. Download each image into a temp dir; return `OcrOutput` so the
//!    caller persists images under the project root.

use std::time::Duration;

use super::OcrOutput;
use crate::parsers::doc_types::ImageRef;

/// Default model. Override via `PADDLEOCR_MODEL`.
const DEFAULT_MODEL: &str = "PaddleOCR-VL-1.6";

pub fn online_is_available() -> bool {
    std::env::var("PADDLEOCR_API_KEY")
        .map(|k| !k.trim().is_empty())
        .unwrap_or(false)
}

pub async fn run_online(pdf_path: &str) -> Result<OcrOutput, String> {
    let pdf_path_owned = pdf_path.to_owned();
    let raw = tokio::task::spawn_blocking(move || -> Result<RawPaddle, String> {
        let host = std::env::var("PADDLEOCR_HOST")
            .unwrap_or_else(|_| "https://paddleocr.aistudio-app.com".to_string());
        let token = std::env::var("PADDLEOCR_API_KEY").unwrap_or_default();
        let model = std::env::var("PADDLEOCR_MODEL").unwrap_or_else(|_| DEFAULT_MODEL.into());
        let client = reqwest::blocking::Client::builder()
            .timeout(Duration::from_secs(600))
            .build()
            .map_err(|e| format!("PaddleOCR HTTP client build failed: {e}"))?;
        let auth = format!("bearer {token}");
        let job_url = format!("{}/api/v2/ocr/jobs", host.trim_end_matches('/'));

        // Step 1: submit
        let optional = serde_json::json!({
            "useDocOrientationClassify": false,
            "useDocUnwarping": false,
            "useChartRecognition": false,
        });
        let job_id = if pdf_path_owned.starts_with("http://") || pdf_path_owned.starts_with("https://") {
            // URL mode
            let payload = serde_json::json!({
                "fileUrl": pdf_path_owned,
                "model": model,
                "optionalPayload": optional,
            });
            let resp = client
                .post(&job_url)
                .header("Authorization", &auth)
                .json(&payload)
                .send()
                .map_err(|e| format!("PaddleOCR submit (url) failed: {e}"))?;
            parse_job_id(resp)?
        } else {
            // Local file mode
            let form = reqwest::blocking::multipart::Form::new()
                .text("model", model)
                .text("optionalPayload", serde_json::to_string(&optional).unwrap_or_default())
                .file("file", &pdf_path_owned)
                .map_err(|e| format!("PaddleOCR multipart build failed: {e}"))?;
            let resp = client
                .post(&job_url)
                .header("Authorization", &auth)
                .multipart(form)
                .send()
                .map_err(|e| format!("PaddleOCR submit (file) failed: {e}"))?;
            parse_job_id(resp)?
        };

        // Step 2: poll
        let mut jsonl_url = String::new();
        for _attempt in 0..240 {
            // 240 * 5s = 20min upper bound
            std::thread::sleep(Duration::from_secs(5));
            let resp = client
                .get(format!("{job_url}/{job_id}"))
                .header("Authorization", &auth)
                .send()
                .map_err(|e| format!("PaddleOCR poll failed: {e}"))?;
            let status = resp.status();
            let body: serde_json::Value = resp
                .json()
                .map_err(|e| format!("PaddleOCR poll parse failed (HTTP {status}): {e}"))?;
            let state = body["data"]["state"].as_str().unwrap_or("");
            match state {
                "done" => {
                    jsonl_url = body["data"]["resultUrl"]["jsonUrl"]
                        .as_str()
                        .ok_or_else(|| "PaddleOCR done but no jsonUrl".to_string())?
                        .to_string();
                    break;
                }
                "failed" => {
                    let msg = body["data"]["errorMsg"].as_str().unwrap_or("unknown");
                    return Err(format!("PaddleOCR job failed: {msg}"));
                }
                _ => continue, // pending / running
            }
        }
        if jsonl_url.is_empty() {
            return Err("PaddleOCR timeout (20 min)".into());
        }

        // Step 3: fetch JSONL
        let jsonl_resp = client
            .get(&jsonl_url)
            .send()
            .map_err(|e| format!("PaddleOCR JSONL fetch failed: {e}"))?;
        if !jsonl_resp.status().is_success() {
            return Err(format!(
                "PaddleOCR JSONL HTTP {}: {}",
                jsonl_resp.status(),
                jsonl_resp.text().unwrap_or_default()
            ));
        }
        let jsonl_text = jsonl_resp
            .text()
            .map_err(|e| format!("PaddleOCR JSONL read failed: {e}"))?;

        // Step 4: parse JSONL → markdown + image URLs
        let mut combined_md = String::new();
        let mut image_urls: Vec<(String, String)> = vec![]; // (name, url)
        for line in jsonl_text.lines() {
            let line = line.trim();
            if line.is_empty() {
                continue;
            }
            let v: serde_json::Value = match serde_json::from_str(line) {
                Ok(x) => x,
                Err(_) => continue,
            };
            let layouts = v["result"]["layoutParsingResults"]
                .as_array()
                .cloned()
                .unwrap_or_default();
            for layout in layouts {
                if let Some(text) = layout["markdown"]["text"].as_str() {
                    combined_md.push_str(text);
                    combined_md.push_str("\n\n");
                }
                if let Some(images) = layout["markdown"]["images"].as_object() {
                    for (name, url_val) in images {
                        if let Some(url) = url_val.as_str() {
                            image_urls.push((name.clone(), url.to_string()));
                        }
                    }
                }
                if let Some(outputs) = layout["outputImages"].as_object() {
                    for (name, url_val) in outputs {
                        if let Some(url) = url_val.as_str() {
                            image_urls.push((format!("output_{name}"), url.to_string()));
                        }
                    }
                }
            }
        }

        // Step 5: download images to temp dir
        let tmp_dir = tempfile::tempdir().map_err(|e| format!("tempdir: {e}"))?;
        let mut images = Vec::with_capacity(image_urls.len());
        for (i, (name, url)) in image_urls.iter().enumerate() {
            let resp = match client.get(url).send() {
                Ok(r) => r,
                Err(_) => continue,
            };
            let bytes = match resp.bytes() {
                Ok(b) => b,
                Err(_) => continue,
            };
            let ext = url.rsplit('.').next().unwrap_or("png");
            let ext = ext
                .chars()
                .take_while(|c| c.is_ascii_alphanumeric())
                .collect::<String>();
            let ext = if ext.is_empty() { "png".to_string() } else { ext };
            let safe_name = format!("paddle_{i:04}_{}.{}", sanitize(name), ext);
            let dest = tmp_dir.path().join(&safe_name);
            if std::fs::write(&dest, &bytes).is_err() {
                continue;
            }
            images.push(ImageRef {
                filename: safe_name,
                page: i,
                region: None,
                description: None,
                esmiles: None,
                rel_path: Some(dest.to_string_lossy().to_string()),
            });
        }

        Ok(RawPaddle {
            text: combined_md,
            images,
        })
    })
    .await
    .map_err(|e| format!("PaddleOCR task join error: {e}"))??;

    Ok(OcrOutput {
        text: raw.text,
        page_count: 0,
        ocr_blocks: vec![],
        images: raw.images,
    })
}

fn parse_job_id(resp: reqwest::blocking::Response) -> Result<String, String> {
    let status = resp.status();
    if !status.is_success() {
        return Err(format!(
            "PaddleOCR submit HTTP {}: {}",
            status,
            resp.text().unwrap_or_default()
        ));
    }
    let body: serde_json::Value = resp
        .json()
        .map_err(|e| format!("PaddleOCR submit parse failed (HTTP {status}): {e}"))?;
    body["data"]["jobId"]
        .as_str()
        .map(|s| s.to_string())
        .ok_or_else(|| "PaddleOCR response missing data.jobId".into())
}

fn sanitize(name: &str) -> String {
    name.chars()
        .map(|c| if c.is_ascii_alphanumeric() || c == '_' || c == '-' { c } else { '_' })
        .collect()
}

struct RawPaddle {
    text: String,
    images: Vec<ImageRef>,
}

// ---------------------------------------------------------------------------
// Local (stub)
// ---------------------------------------------------------------------------

pub fn local_is_available() -> bool {
    true
}

pub async fn warmup_local() -> Result<(), String> {
    Err("paddleocr_local_warmup_not_implemented".into())
}

pub async fn run_local(_pdf_path: &str) -> Result<OcrOutput, String> {
    Err("paddleocr_local_not_implemented".into())
}

/// Trait wrapper for the PaddleOCR online backend.
pub struct PaddleOnlineBackend;

#[async_trait::async_trait]
impl crate::parsers::ocr::backend::OcrBackend for PaddleOnlineBackend {
    fn name(&self) -> &'static str {
        "paddleocr-online"
    }

    fn is_available(&self) -> bool {
        online_is_available()
    }

    async fn run(&self, path: &str) -> Result<crate::parsers::ocr::backend::OcrOutput, String> {
        run_online(path).await
    }
}

/// Trait wrapper for the PaddleOCR local backend.
pub struct PaddleLocalBackend;

#[async_trait::async_trait]
impl crate::parsers::ocr::backend::OcrBackend for PaddleLocalBackend {
    fn name(&self) -> &'static str {
        "paddleocr-local"
    }

    fn is_available(&self) -> bool {
        local_is_available()
    }

    async fn run(&self, path: &str) -> Result<crate::parsers::ocr::backend::OcrOutput, String> {
        run_local(path).await
    }
}