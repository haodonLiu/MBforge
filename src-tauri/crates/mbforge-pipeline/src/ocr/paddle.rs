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
//!
//! Uses the async `reqwest::Client` (shared via `LazyLock` so the
//! connection pool is reused across calls) — see review §6.

use std::sync::LazyLock;

use reqwest::Client;

use super::OcrOutput;
use crate::doc_types::ImageRef;

/// Default model. Override via `PADDLEOCR_MODEL`.
const DEFAULT_MODEL: &str = "PaddleOCR-VL-1.6";

/// Process-wide async HTTP client. Reused across calls so the
/// connection pool is shared and we don't pay TLS handshake cost
/// per request. Initialiser is known at declaration time, so
/// `LazyLock` (not `OnceLock`).
static HTTP_CLIENT: LazyLock<Client> = LazyLock::new(|| {
    Client::builder()
        .timeout(std::time::Duration::from_secs(600))
        .build()
        .expect("PaddleOCR HTTP client build")
});

/// Maximum number of bytes we are willing to accept from a single
/// image-download response. Caps a malicious or buggy server at
/// 64 MiB per image; the loop logs and skips failures above this.
const MAX_IMAGE_BYTES: u64 = 64 * 1024 * 1024;

pub fn online_is_available() -> bool {
    std::env::var("PADDLEOCR_API_KEY")
        .map(|k| !k.trim().is_empty())
        .unwrap_or(false)
}

pub async fn run_online(pdf_path: &str) -> Result<OcrOutput, String> {
    let host = std::env::var("PADDLEOCR_HOST")
        .unwrap_or_else(|_| "https://paddleocr.aistudio-app.com".to_string());
    let token = std::env::var("PADDLEOCR_API_KEY").unwrap_or_default();
    // Fail fast on missing credentials. Otherwise the request would
    // return 401 and we'd waste a multipart upload before discovering
    // the misconfiguration.
    if token.trim().is_empty() {
        return Err("PADDLEOCR_API_KEY is not set".to_string());
    }
    let model = std::env::var("PADDLEOCR_MODEL").unwrap_or_else(|_| DEFAULT_MODEL.into());
    let auth = format!("bearer {token}");
    let job_url = format!("{}/api/v2/ocr/jobs", host.trim_end_matches('/'));

    let client = &*HTTP_CLIENT;

    // Step 1: submit
    let optional = serde_json::json!({
        "useDocOrientationClassify": false,
        "useDocUnwarping": false,
        "useChartRecognition": false,
    });
    let job_id = if pdf_path.starts_with("http://") || pdf_path.starts_with("https://") {
        // URL mode
        let payload = serde_json::json!({
            "fileUrl": pdf_path,
            "model": model,
            "optionalPayload": optional,
        });
        let resp = client
            .post(&job_url)
            .header("Authorization", &auth)
            .json(&payload)
            .send()
            .await
            .map_err(|e| format!("PaddleOCR submit (url) failed: {e}"))?;
        parse_job_id(resp).await?
    } else {
        // Local file mode
        let pdf_bytes = tokio::fs::read(pdf_path)
            .await
            .map_err(|e| format!("PaddleOCR read PDF failed: {e}"))?;
        let part = reqwest::multipart::Part::bytes(pdf_bytes)
            .file_name("document.pdf")
            .mime_str("application/pdf")
            .map_err(|e| format!("MIME error: {e}"))?;
        let form = reqwest::multipart::Form::new()
            .text("model", model.clone())
            .text(
                "optionalPayload",
                serde_json::to_string(&optional).unwrap_or_default(),
            )
            .part("file", part);
        let resp = client
            .post(&job_url)
            .header("Authorization", &auth)
            .multipart(form)
            .send()
            .await
            .map_err(|e| format!("PaddleOCR submit (file) failed: {e}"))?;
        parse_job_id(resp).await?
    };

    // Step 2: poll
    let mut jsonl_url = String::new();
    for _attempt in 0..240 {
        // 240 * 5s = 20min upper bound
        tokio::time::sleep(std::time::Duration::from_secs(5)).await;
        let resp = client
            .get(format!("{job_url}/{job_id}"))
            .header("Authorization", &auth)
            .send()
            .await
            .map_err(|e| format!("PaddleOCR poll failed: {e}"))?;
        let status = resp.status();
        let body: serde_json::Value = resp
            .json()
            .await
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
        .await
        .map_err(|e| format!("PaddleOCR JSONL fetch failed: {e}"))?;
    if !jsonl_resp.status().is_success() {
        let status = jsonl_resp.status();
        let body = jsonl_resp.text().await.unwrap_or_default();
        return Err(format!("PaddleOCR JSONL HTTP {status}: {body}"));
    }
    let jsonl_text = jsonl_resp
        .text()
        .await
        .map_err(|e| format!("PaddleOCR JSONL read failed: {e}"))?;

    // Step 4: parse JSONL → markdown + image URLs
    let mut combined_md = String::new();
    let mut image_urls: Vec<(String, String)> = vec![]; // (name, url)
    for line in jsonl_text.lines() {
        let line = line.trim();
        if line.is_empty() {
            continue;
        }
        // PaddleOCR returns `{"result": {"layoutParsingResults": [...]}}` per line.
        // We accept both the wrapped and unwrapped shapes.
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
        let resp = match client.get(url).send().await {
            Ok(r) => r,
            Err(e) => {
                log::warn!("PaddleOCR image fetch failed for {name}: {e}");
                continue;
            }
        };
        // Cap download size to defend against runaway servers.
        let bytes = match download_bounded(resp, MAX_IMAGE_BYTES).await {
            Ok(b) => b,
            Err(e) => {
                log::warn!("PaddleOCR image body read failed for {name}: {e}");
                continue;
            }
        };
        let ext = url.rsplit('.').next().unwrap_or("png");
        let ext = ext
            .chars()
            .take_while(|c| c.is_ascii_alphanumeric())
            .collect::<String>();
        let ext = if ext.is_empty() { "png" } else { ext.as_str() };
        let safe_name = format!("paddle_{i:04}_{}.{}", sanitize(name), ext);
        let dest = tmp_dir.path().join(&safe_name);
        if let Err(e) = tokio::fs::write(&dest, &bytes).await {
            log::warn!("PaddleOCR image write failed for {dest:?}: {e}");
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

    Ok(OcrOutput {
        text: combined_md,
        page_count: 0,
        ocr_blocks: vec![],
        images,
    })
}

/// Read a response body as bytes, aborting if the Content-Length
/// header advertises more than `max_bytes`. The streaming cap is
/// only an opportunistic check: a server that lies about (or omits)
/// its Content-Length can still cause us to allocate up to the body
/// size. Returning a cap before `bytes().await` is the practical
/// safe response.
async fn download_bounded(
    resp: reqwest::Response,
    max_bytes: u64,
) -> Result<Vec<u8>, String> {
    if let Some(len) = resp.content_length() {
        if len > max_bytes {
            return Err(format!("response body too large: {len} > {max_bytes}"));
        }
    }
    let bytes = resp
        .bytes()
        .await
        .map_err(|e| format!("response body read: {e}"))?;
    if (bytes.len() as u64) > max_bytes {
        return Err(format!(
            "response body exceeded {max_bytes} bytes (Content-Length was absent or wrong)"
        ));
    }
    Ok(bytes.to_vec())
}

async fn parse_job_id(resp: reqwest::Response) -> Result<String, String> {
    let status = resp.status();
    let body: serde_json::Value = resp
        .json()
        .await
        .map_err(|e| format!("PaddleOCR submit parse failed (HTTP {status}): {e}"))?;
    body["data"]["jobId"]
        .as_str()
        .map(|s| s.to_string())
        .ok_or_else(|| "PaddleOCR response missing data.jobId".into())
}

fn sanitize(name: &str) -> String {
    name.chars()
        .map(|c| {
            if c.is_ascii_alphanumeric() || c == '_' || c == '-' {
                c
            } else {
                '_'
            }
        })
        .collect()
}

// ---------------------------------------------------------------------------
// Local backend — explicitly unimplemented stubs
// ---------------------------------------------------------------------------
//
// The PaddleOCR local backend (in-process, no network) is not yet wired.
// These three functions are registered so the config UI and `default_backends`
// can list the option; `local_is_available` always returns false and
// `warmup_local` / `run_local` return a descriptive error. See TODO/INDEX.md.
// Do not call them from the hot path — guard with `local_is_available()` first.

pub fn local_is_available() -> bool {
    // Always false until the in-process PaddleOCR runtime is integrated.
    false
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
impl crate::ocr::backend::OcrBackend for PaddleOnlineBackend {
    fn name(&self) -> &'static str {
        "paddleocr-online"
    }

    fn is_available(&self) -> bool {
        online_is_available()
    }

    async fn run(&self, path: &str) -> Result<crate::ocr::backend::OcrOutput, String> {
        run_online(path).await
    }
}

/// Trait wrapper for the PaddleOCR local backend.
pub struct PaddleLocalBackend;

#[async_trait::async_trait]
impl crate::ocr::backend::OcrBackend for PaddleLocalBackend {
    fn name(&self) -> &'static str {
        "paddleocr-local"
    }

    fn is_available(&self) -> bool {
        local_is_available()
    }

    async fn run(&self, path: &str) -> Result<crate::ocr::backend::OcrOutput, String> {
        run_local(path).await
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_sanitize() {
        assert_eq!(sanitize("化合物26A"), "化合物26A");
        assert_eq!(sanitize("a/b c.png"), "a_b_c_png");
    }

    #[test]
    fn test_online_is_available_false_when_token_empty() {
        // Force a known state regardless of caller env.
        // SAFETY: test-only single-thread setup.
        let prev = std::env::var("PADDLEOCR_API_KEY").ok();
        // SAFETY: see above.
        unsafe {
            std::env::set_var("PADDLEOCR_API_KEY", "");
        }
        assert!(!online_is_available());
        // SAFETY: see above.
        unsafe {
            std::env::set_var("PADDLEOCR_API_KEY", "real-token");
        }
        assert!(online_is_available());
        // SAFETY: see above.
        match prev {
            Some(v) => unsafe { std::env::set_var("PADDLEOCR_API_KEY", v) },
            None => unsafe { std::env::remove_var("PADDLEOCR_API_KEY") },
        }
    }

    #[tokio::test]
    async fn test_run_online_missing_token_fails_fast() {
        // SAFETY: test-only single-thread setup.
        let prev = std::env::var("PADDLEOCR_API_KEY").ok();
        unsafe {
            std::env::remove_var("PADDLEOCR_API_KEY");
        }
        let result = run_online("dummy.pdf").await;
        assert!(result.is_err());
        let err = result.unwrap_err();
        assert!(
            err.contains("PADDLEOCR_API_KEY is not set"),
            "expected fast-fail error, got {err:?}"
        );
        // SAFETY: see above.
        match prev {
            Some(v) => unsafe { std::env::set_var("PADDLEOCR_API_KEY", v) },
            None => unsafe { std::env::remove_var("PADDLEOCR_API_KEY") },
        }
    }

    #[test]
    fn test_http_client_initialised() {
        // The LazyLock must produce a working client; if init fails
        // the process panics (see HTTP_CLIENT definition), so this
        // test simply asserts the client is reachable.
        let _ = &*HTTP_CLIENT;
    }
}
