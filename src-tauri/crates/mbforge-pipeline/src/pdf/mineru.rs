#![allow(dead_code)]
use std::path::Path;

use crate::doc_types::{ImageRef, OcrBlock};

/// Maximum bytes we will accept in a single MinerU zip response
/// (advertised by Content-Length). 512 MiB is generous for a
/// research paper and well above any single MinerU output.
const MAX_ZIP_BYTES: u64 = 512 * 1024 * 1024;

/// Maximum number of entries we will extract from a single zip.
/// Defends against zip-bombs that use a huge central directory.
const MAX_ZIP_ENTRIES: usize = 50_000;

/// Maximum uncompressed bytes per zip entry (advisory; the zip
/// crate does not enforce this — it trusts the header).
const MAX_ZIP_ENTRY_BYTES: u64 = 256 * 1024 * 1024;

// ---------------------------------------------------------------------------
// Options & Result
// ---------------------------------------------------------------------------

/// MinerU API 调用选项 — 基于官方文档的完整参数集。
///
/// 参考: https://mineru.net/apiManage/docs
#[derive(Debug, Clone)]
pub struct MineruOptions {
    /// 是否启用 OCR。默认 `false`，扫描文档**必须**设为 `true`。
    /// 仅对 `pipeline` / `vlm` 模型有效。
    pub is_ocr: bool,
    /// 文档语言。默认 `"ch"`（中文+英文）。
    /// 英文文档建议 `"en"`，日文 `"japan"`，韩文 `"korean"` 等。
    pub language: String,
    /// 页面范围，如 `"1-20"`、`"2,4-6"`、`"2--2"`（从第2页到倒数第2页）。
    /// `None` 表示解析全部页面。
    pub page_ranges: Option<String>,
    /// 是否启用公式识别。默认 `true`。
    /// 对 `vlm` 模型仅影响行内公式提取。
    pub enable_formula: bool,
    /// 是否启用表格识别。默认 `true`。
    pub enable_table: bool,
    /// 模型版本: `"pipeline"` / `"vlm"`(推荐) / `"MinerU-HTML"`。
    pub model_version: String,
    /// 额外导出格式。默认空（只输出 Markdown + JSON）。
    /// 可选 `"docx"`、`"html"`、`"latex"`。
    pub extra_formats: Vec<String>,
}

impl Default for MineruOptions {
    fn default() -> Self {
        Self {
            is_ocr: false,
            language: "ch".into(),
            page_ranges: None,
            enable_formula: true,
            enable_table: true,
            model_version: "vlm".into(),
            extra_formats: vec![],
        }
    }
}

/// MinerU 解析结果。
pub struct MineruResult {
    /// Markdown 文本内容。
    pub markdown: String,
    /// 提取的图片（来自 zip 包 `images/` 目录）。
    pub images: Vec<ImageRef>,
    /// OCR 布局块（来自 zip 包 `layout.json`）。
    pub ocr_blocks: Vec<OcrBlock>,
    /// 解析来源标识。
    pub source: String,
    /// 任务 ID。
    pub task_id: String,
}

// ---------------------------------------------------------------------------
// Client
// ---------------------------------------------------------------------------

/// MinerU API client — supports both Precise and Agent APIs.
///
/// Precise API: https://mineru.net/api/v4/ (needs Token)
/// Agent API:   https://mineru.net/api/v1/agent/ (no Token, IP rate-limited)
pub struct MineruClient {
    host: String,
    api_key: String,
    client: reqwest::blocking::Client,
}

impl MineruClient {
    /// Create a new client.
    /// If api_key is empty, uses the Agent API (no auth required).
    pub fn new(host: &str, api_key: &str) -> Self {
        let client = reqwest::blocking::Client::builder()
            .timeout(std::time::Duration::from_secs(600))
            .build()
            .expect("Failed to create HTTP client");

        Self {
            host: host.trim_end_matches('/').to_string(),
            api_key: api_key.to_string(),
            client,
        }
    }

    /// Whether this client uses the Agent API (no token).
    fn is_agent(&self) -> bool {
        self.api_key.is_empty()
    }

    /// Parse a PDF via URL with options.
    pub fn parse_url_with_options(
        &self,
        url: &str,
        options: &MineruOptions,
    ) -> Result<MineruResult, String> {
        let task_id = self.submit_url(url, options)?;
        self.wait_for_completion(&task_id, options)
    }

    /// Parse a PDF via URL with default options.
    pub fn parse_url(&self, url: &str) -> Result<MineruResult, String> {
        self.parse_url_with_options(url, &MineruOptions::default())
    }

    /// Parse a local PDF file with options.
    pub fn parse_file_with_options(
        &self,
        file_path: &str,
        options: &MineruOptions,
    ) -> Result<MineruResult, String> {
        if self.is_agent() {
            self.parse_file_agent(file_path, options)
        } else {
            self.parse_file_precise(file_path, options)
        }
    }

    /// Parse a local PDF file with default options.
    pub fn parse_file(&self, file_path: &str) -> Result<MineruResult, String> {
        self.parse_file_with_options(file_path, &MineruOptions::default())
    }

    // ---- Agent API (no token) ----

    fn submit_url_agent(&self, url: &str, options: &MineruOptions) -> Result<String, String> {
        let api_url = format!("{}/api/v1/agent/parse/url", self.host);
        let mut body = serde_json::json!({
            "url": url,
            "language": options.language,
            "enable_table": options.enable_table,
            "enable_formula": options.enable_formula,
            "is_ocr": options.is_ocr,
        });
        if let Some(ref pr) = options.page_ranges {
            body["page_range"] = serde_json::json!(pr);
        }

        let resp = self
            .client
            .post(&api_url)
            .json(&body)
            .send()
            .map_err(|e| format!("MinerU agent request failed: {}", e))?;

        let result: serde_json::Value = resp
            .json()
            .map_err(|e| format!("MinerU response error: {}", e))?;

        if result["code"].as_i64() != Some(0) {
            return Err(format!("MinerU error: {}", result["msg"]));
        }

        result["data"]["task_id"]
            .as_str()
            .map(|s: &str| s.to_string())
            .ok_or_else(|| "No task_id in response".into())
    }

    fn poll_agent(&self, task_id: &str) -> Result<MineruResult, String> {
        let api_url = format!("{}/api/v1/agent/parse/{}", self.host, task_id);
        let mut attempts = 0;

        loop {
            let resp = self
                .client
                .get(&api_url)
                .send()
                .map_err(|e| format!("MinerU poll failed: {}", e))?;

            let result: serde_json::Value = resp
                .json()
                .map_err(|e| format!("MinerU poll response error: {}", e))?;

            if result["code"].as_i64() != Some(0) {
                return Err(format!("MinerU error: {}", result["msg"]));
            }

            let state = result["data"]["state"].as_str().unwrap_or("");
            match state {
                "done" => {
                    let md_url = result["data"]["markdown_url"].as_str().unwrap_or("");
                    let markdown = if !md_url.is_empty() {
                        self.client
                            .get(md_url)
                            .send()
                            .map_err(|e| format!("Failed to download markdown: {}", e))?
                            .text()
                            .map_err(|e| format!("Failed to read markdown: {}", e))?
                    } else {
                        String::new()
                    };
                    return Ok(MineruResult {
                        markdown,
                        images: vec![],     // Agent API 不返回图片
                        ocr_blocks: vec![], // Agent API 不返回 layout
                        source: "mineru_agent".into(),
                        task_id: task_id.to_string(),
                    });
                }
                "failed" => {
                    let err = result["data"]["err_msg"].as_str().unwrap_or("unknown");
                    return Err(format!("MinerU parse failed: {}", err));
                }
                _ => {
                    attempts += 1;
                    if attempts > 200 {
                        return Err("MinerU timeout (10 min)".into());
                    }
                    std::thread::sleep(std::time::Duration::from_secs(3));
                }
            }
        }
    }

    fn parse_file_agent(
        &self,
        file_path: &str,
        options: &MineruOptions,
    ) -> Result<MineruResult, String> {
        let filename = std::path::Path::new(file_path)
            .file_name()
            .and_then(|n| n.to_str())
            .unwrap_or("document.pdf");

        // Step 1: Get signed upload URL
        let api_url = format!("{}/api/v1/agent/parse/file", self.host);
        let mut body = serde_json::json!({
            "file_name": filename,
            "language": options.language,
            "enable_table": options.enable_table,
            "enable_formula": options.enable_formula,
            "is_ocr": options.is_ocr,
        });
        if let Some(ref pr) = options.page_ranges {
            body["page_range"] = serde_json::json!(pr);
        }

        let resp = self
            .client
            .post(&api_url)
            .json(&body)
            .send()
            .map_err(|e| format!("MinerU agent file request failed: {}", e))?;

        let result: serde_json::Value = resp
            .json()
            .map_err(|e| format!("MinerU response error: {}", e))?;

        if result["code"].as_i64() != Some(0) {
            return Err(format!("MinerU error: {}", result["msg"]));
        }

        let task_id = result["data"]["task_id"]
            .as_str()
            .ok_or("No task_id")?
            .to_string();
        let file_url = result["data"]["file_url"]
            .as_str()
            .ok_or("No file_url")?
            .to_string();

        // Step 2: PUT file to OSS
        let file_bytes =
            std::fs::read(file_path).map_err(|e| format!("Failed to read file: {}", e))?;
        self.client
            .put(&file_url)
            .body(file_bytes)
            .send()
            .map_err(|e| format!("Failed to upload file: {}", e))?;

        // Step 3: Poll for result
        self.poll_agent(&task_id)
    }

    // ---- Precise API (with token) ----

    fn build_request_body(&self, options: &MineruOptions) -> serde_json::Value {
        let mut body = serde_json::json!({
            "model_version": options.model_version,
            "enable_formula": options.enable_formula,
            "enable_table": options.enable_table,
            "language": options.language,
            "is_ocr": options.is_ocr,
        });
        if let Some(ref pr) = options.page_ranges {
            body["page_ranges"] = serde_json::json!(pr);
        }
        if !options.extra_formats.is_empty() {
            body["extra_formats"] = serde_json::json!(&options.extra_formats);
        }
        body
    }

    fn submit_url_precise(&self, url: &str, options: &MineruOptions) -> Result<String, String> {
        let api_url = format!("{}/api/v4/extract/task", self.host);
        let mut body = self.build_request_body(options);
        body["url"] = serde_json::json!(url);

        let resp = self
            .client
            .post(&api_url)
            .header("Authorization", format!("Bearer {}", self.api_key))
            .json(&body)
            .send()
            .map_err(|e| format!("MinerU precise request failed: {}", e))?;

        let result: serde_json::Value = resp
            .json()
            .map_err(|e| format!("MinerU response error: {}", e))?;

        if result["code"].as_i64() != Some(0) {
            return Err(format!("MinerU error: {}", result["msg"]));
        }

        result["data"]["task_id"]
            .as_str()
            .map(|s: &str| s.to_string())
            .ok_or_else(|| "No task_id in response".into())
    }

    fn poll_precise(
        &self,
        task_id: &str,
        _options: &MineruOptions,
    ) -> Result<MineruResult, String> {
        let api_url = format!("{}/api/v4/extract/task/{}", self.host, task_id);
        let mut attempts = 0;

        loop {
            let resp = self
                .client
                .get(&api_url)
                .header("Authorization", format!("Bearer {}", self.api_key))
                .send()
                .map_err(|e| format!("MinerU poll failed: {}", e))?;

            let result: serde_json::Value = resp
                .json()
                .map_err(|e| format!("MinerU poll response error: {}", e))?;

            if result["code"].as_i64() != Some(0) {
                return Err(format!("MinerU error: {}", result["msg"]));
            }

            let state = result["data"]["state"].as_str().unwrap_or("");
            match state {
                "done" => {
                    let zip_url = result["data"]["full_zip_url"].as_str().unwrap_or("");
                    if !zip_url.is_empty() {
                        return self.download_and_extract(zip_url, task_id);
                    }
                    return Ok(MineruResult {
                        markdown: String::new(),
                        images: vec![],
                        ocr_blocks: vec![],
                        source: "mineru_precise".into(),
                        task_id: task_id.to_string(),
                    });
                }
                "failed" => {
                    let err = result["data"]["err_msg"].as_str().unwrap_or("unknown");
                    return Err(format!("MinerU parse failed: {}", err));
                }
                _ => {
                    attempts += 1;
                    if attempts > 200 {
                        return Err("MinerU timeout (10 min)".into());
                    }
                    std::thread::sleep(std::time::Duration::from_secs(3));
                }
            }
        }
    }

    /// 下载 zip 包并提取 markdown + images。
    fn download_and_extract(&self, zip_url: &str, task_id: &str) -> Result<MineruResult, String> {
        // Download zip to temp file
        let mut resp = self
            .client
            .get(zip_url)
            .send()
            .map_err(|e| format!("Failed to download zip: {}", e))?;
        // Pre-check Content-Length so honest servers that advertise
        // an oversize response fail fast before we start writing.
        if let Some(len) = resp.content_length() {
            if len > MAX_ZIP_BYTES {
                return Err(format!(
                    "MinerU zip too large (Content-Length {len} > {MAX_ZIP_BYTES})"
                ));
            }
        }

        let tmp_dir = tempfile::tempdir().map_err(|e| format!("Temp dir error: {}", e))?;
        let zip_path = tmp_dir.path().join("result.zip");

        // Stream the response body to disk in 32 KiB chunks with a
        // hard byte cap (`Take` from `std::io`). This avoids the OOM
        // that `resp.bytes()` would cause on a multi-GB response
        // and stops a malicious / buggy server that lies about (or
        // omits) Content-Length at MAX_ZIP_BYTES.
        {
            use std::io::Read;
            let mut out = std::fs::File::create(&zip_path)
                .map_err(|e| format!("Failed to create zip file: {}", e))?;
            let mut limited = (&mut resp).take(MAX_ZIP_BYTES);
            let mut buf = [0u8; 32 * 1024];
            loop {
                let n = limited
                    .read(&mut buf)
                    .map_err(|e| format!("Failed to read zip: {}", e))?;
                if n == 0 {
                    break;
                }
                std::io::Write::write_all(&mut out, &buf[..n])
                    .map_err(|e| format!("Failed to write zip: {}", e))?;
            }
        }

        // Extract zip
        let zip_file =
            std::fs::File::open(&zip_path).map_err(|e| format!("Failed to open zip: {}", e))?;
        let mut archive = zip::ZipArchive::new(zip_file)
            .map_err(|e| format!("Failed to read zip archive: {}", e))?;

        let mut markdown = String::new();
        let mut image_refs: Vec<ImageRef> = Vec::new();
        let mut ocr_blocks: Vec<OcrBlock> = Vec::new();
        let mut layout_json_data: Option<serde_json::Value> = None;

        // 先确定解压目标目录：当前工作目录下的 .mbforge/mineru-tmp/ 或临时目录
        let extract_base = tmp_dir.path().join("extracted");
        std::fs::create_dir_all(&extract_base).ok();

        // Defend against zip-bombs: cap the total number of entries
        // and the uncompressed size of any single entry. The zip
        // crate trusts header values, so an oversize entry could
        // still OOM during decompression; we skip those rather than
        // fail so a single bad asset doesn't kill the whole run.
        if archive.len() > MAX_ZIP_ENTRIES {
            return Err(format!(
                "MinerU zip has too many entries ({} > {MAX_ZIP_ENTRIES})",
                archive.len()
            ));
        }
         for i in 0..archive.len() {
            let mut entry = archive
                .by_index(i)
                .map_err(|e| format!("Zip entry error: {}", e))?;
            let name = entry.name().to_string();

            // Skip oversize entries (advisory — see MAX_ZIP_ENTRY_BYTES).
            if entry.size() > MAX_ZIP_ENTRY_BYTES {
                log::warn!(
                    "[mineru] zip entry {name} too large ({} > {}), skipping",
                    entry.size(),
                    MAX_ZIP_ENTRY_BYTES
                );
                continue;
            }

            // 提取图片
            if name.starts_with("images/") && !name.ends_with('/') {
                let filename = Path::new(&name)
                    .file_name()
                    .and_then(|n| n.to_str())
                    .unwrap_or(&name)
                    .to_string();
                let dest = extract_base.join(&filename);
                let mut out = std::fs::File::create(&dest)
                    .map_err(|e| format!("Failed to create image file: {}", e))?;
                std::io::copy(&mut entry, &mut out)
                    .map_err(|e| format!("Failed to extract image: {}", e))?;

                image_refs.push(ImageRef {
                    filename: filename.clone(),
                    page: 0, // MinerU 图片名不含页码信息，无法直接推断
                    region: None,
                    description: None,
                    esmiles: None,
                    rel_path: Some(dest.to_string_lossy().to_string()),
                });
            }
            // 提取 markdown（优先 full.md）
            else if name.ends_with("full.md")
                || name.ends_with("full_markdown.md")
                || (name.ends_with(".md") && markdown.is_empty())
            {
                std::io::Read::read_to_string(&mut std::io::BufReader::new(entry), &mut markdown)
                    .map_err(|e| format!("Failed to read markdown from zip: {}", e))?;
            }
            // 解析 layout.json
            else if name.ends_with("layout.json") {
                let mut content = String::new();
                std::io::Read::read_to_string(&mut std::io::BufReader::new(entry), &mut content)
                    .map_err(|e| format!("Failed to read layout.json: {}", e))?;
                layout_json_data = serde_json::from_str(&content).ok();
            }
        }

        if markdown.is_empty() {
            return Err("No markdown file found in zip".into());
        }

        // 解析 layout.json 提取 OCR 块
        if let Some(layout) = layout_json_data {
            ocr_blocks = parse_layout_json(&layout);
        }

        Ok(MineruResult {
            markdown,
            images: image_refs,
            ocr_blocks,
            source: "mineru_precise".into(),
            task_id: task_id.to_string(),
        })
    }

    fn parse_file_precise(
        &self,
        file_path: &str,
        options: &MineruOptions,
    ) -> Result<MineruResult, String> {
        let filename = std::path::Path::new(file_path)
            .file_name()
            .and_then(|n| n.to_str())
            .unwrap_or("document.pdf");

        let api_url = format!("{}/api/v4/file-urls/batch", self.host);
        let mut body = self.build_request_body(options);
        body["files"] = serde_json::json!([{"name": filename}]);

        let resp = self
            .client
            .post(&api_url)
            .header("Authorization", format!("Bearer {}", self.api_key))
            .json(&body)
            .send()
            .map_err(|e| format!("MinerU batch request failed: {}", e))?;

        let result: serde_json::Value = resp
            .json()
            .map_err(|e| format!("MinerU response error: {}", e))?;

        if result["code"].as_i64() != Some(0) {
            return Err(format!("MinerU error: {}", result["msg"]));
        }

        let batch_id = result["data"]["batch_id"]
            .as_str()
            .ok_or("No batch_id")?
            .to_string();
        let upload_url = result["data"]["file_urls"][0]
            .as_str()
            .ok_or("No upload URL")?
            .to_string();

        // Upload file
        let file_bytes =
            std::fs::read(file_path).map_err(|e| format!("Failed to read file: {}", e))?;
        self.client
            .put(&upload_url)
            .body(file_bytes)
            .send()
            .map_err(|e| format!("Failed to upload file: {}", e))?;

        // Poll batch result
        self.poll_batch(&batch_id, options)
    }

    fn poll_batch(&self, batch_id: &str, _options: &MineruOptions) -> Result<MineruResult, String> {
        let api_url = format!("{}/api/v4/extract-results/batch/{}", self.host, batch_id);
        let mut attempts = 0;

        loop {
            let resp = self
                .client
                .get(&api_url)
                .header("Authorization", format!("Bearer {}", self.api_key))
                .send()
                .map_err(|e| format!("MinerU batch poll failed: {}", e))?;

            let result: serde_json::Value = resp
                .json()
                .map_err(|e| format!("MinerU batch response error: {}", e))?;

            if result["code"].as_i64() != Some(0) {
                return Err(format!("MinerU error: {}", result["msg"]));
            }

            let results = result["data"]["extract_result"]
                .as_array()
                .ok_or("No extract_result")?;

            if let Some(first) = results.first() {
                let state = first["state"].as_str().unwrap_or("");
                match state {
                    "done" => {
                        let zip_url = first["full_zip_url"].as_str().unwrap_or("");
                        if !zip_url.is_empty() {
                            return self.download_and_extract(zip_url, batch_id);
                        }
                        return Ok(MineruResult {
                            markdown: String::new(),
                            images: vec![],
                            ocr_blocks: vec![],
                            source: "mineru_precise".into(),
                            task_id: batch_id.to_string(),
                        });
                    }
                    "failed" => {
                        let err = first["err_msg"].as_str().unwrap_or("unknown");
                        return Err(format!("MinerU parse failed: {}", err));
                    }
                    _ => {}
                }
            }

            attempts += 1;
            if attempts > 200 {
                return Err("MinerU timeout (10 min)".into());
            }
            std::thread::sleep(std::time::Duration::from_secs(3));
        }
    }

    fn submit_url(&self, url: &str, options: &MineruOptions) -> Result<String, String> {
        if self.is_agent() {
            self.submit_url_agent(url, options)
        } else {
            self.submit_url_precise(url, options)
        }
    }

    fn wait_for_completion(
        &self,
        task_id: &str,
        options: &MineruOptions,
    ) -> Result<MineruResult, String> {
        if self.is_agent() {
            self.poll_agent(task_id)
        } else {
            self.poll_precise(task_id, options)
        }
    }
}

// ---------------------------------------------------------------------------
// Helper: 根据文件名/路径推断语言
// ---------------------------------------------------------------------------

/// 根据文件路径推断 MinerU 语言参数。
///
/// 规则（按优先级）：
/// 1. 文件名前缀: `CN`/`cn` → `"ch"`, `US`/`us`/`EP`/`ep`/`WO`/`wo` → `"en"`
/// 2. 路径中的语言标识
/// 3. 默认 `"ch"`（中文+英文混合，对英文文档也兼容）
pub fn infer_language_from_path(path: &str) -> String {
    let name = Path::new(path)
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("")
        .to_lowercase();

    if name.starts_with("us") || name.starts_with("ep") || name.starts_with("wo") {
        return "en".into();
    }
    if name.starts_with("cn") {
        return "ch".into();
    }
    // 如果文件名中包含 japanese/korean 等关键词可继续扩展
    "ch".into()
}

/// 为扫描文档构建推荐的 MinerU 选项。
///
/// - `is_ocr`: `true`（必须）
/// - `language`: 根据路径自动推断
/// - `model_version`: `"vlm"`（推荐，OCR 效果最好）
pub fn scanned_pdf_options(path: &str) -> MineruOptions {
    MineruOptions {
        is_ocr: true,
        language: infer_language_from_path(path),
        model_version: "vlm".into(),
        ..MineruOptions::default()
    }
}

// ---------------------------------------------------------------------------
// layout.json 解析
// ---------------------------------------------------------------------------

/// 解析 MinerU layout.json，提取 OCR 块列表。
///
/// layout.json 结构:
/// ```json
/// {
///   "pdf_info": [
///     {
///       "preproc_blocks": [
///         {
///           "bbox": [75, 50, 195, 67],
///           "type": "text",
///           "angle": 0,
///           "lines": [{ "spans": [{ "content": "..." }] }],
///           "index": 2
///         }
///       ]
///     }
///   ]
/// }
/// ```
fn parse_layout_json(layout: &serde_json::Value) -> Vec<OcrBlock> {
    let mut blocks = Vec::new();
    let pdf_info = match layout.get("pdf_info").and_then(|v| v.as_array()) {
        Some(arr) => arr,
        None => return blocks,
    };

    for (page_idx, page) in pdf_info.iter().enumerate() {
        let preproc_blocks = match page.get("preproc_blocks").and_then(|v| v.as_array()) {
            Some(arr) => arr,
            None => continue,
        };

        for block in preproc_blocks {
            let bbox = block.get("bbox").and_then(|v| v.as_array()).map(|arr| {
                let mut b = [0.0f64; 4];
                for (i, val) in arr.iter().take(4).enumerate() {
                    b[i] = val.as_f64().unwrap_or(0.0);
                }
                b
            });

            let block_type = block
                .get("type")
                .and_then(|v| v.as_str())
                .unwrap_or("unknown")
                .to_string();

            let index = block.get("index").and_then(|v| v.as_u64()).unwrap_or(0) as usize;

            let angle = block.get("angle").and_then(|v| v.as_i64()).unwrap_or(0) as i32;

            // 提取文本内容：拼接所有 lines → spans → content
            let content = block.get("lines").and_then(|v| v.as_array()).map(|lines| {
                let mut parts = Vec::new();
                for line in lines {
                    if let Some(spans) = line.get("spans").and_then(|v| v.as_array()) {
                        for span in spans {
                            if let Some(text) = span.get("content").and_then(|v| v.as_str()) {
                                parts.push(text.to_string());
                            }
                        }
                    }
                }
                parts.join(" ")
            });

            if let Some(bbox) = bbox {
                blocks.push(OcrBlock {
                    page: page_idx + 1, // 1-based
                    block_type,
                    bbox,
                    content: if content.as_ref().map(|s| s.is_empty()).unwrap_or(true) {
                        None
                    } else {
                        content
                    },
                    index,
                    angle,
                });
            }
        }
    }

    blocks
}
// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------
mod tests {
    use super::*;

    #[test]
    fn test_zip_caps_are_sane() {
    // 512 MiB zip is generous; 50k entries is well above any
    // reasonable MinerU output. These constants are load-bearing
    // for the OOM + zip-bomb defence — change only with care.
        assert_eq!(MAX_ZIP_BYTES, 512 * 1024 * 1024);
        // for the OOM + zip-bomb defence — change only with care.
        assert_eq!(MAX_ZIP_ENTRIES, 50_000);
        assert_eq!(MAX_ZIP_ENTRY_BYTES, 256 * 1024 * 1024);
        assert!(MAX_ZIP_ENTRY_BYTES < MAX_ZIP_BYTES);
    }

    #[test]
    fn test_infer_language_known_prefixes() {
        assert_eq!(infer_language_from_path("USP2024.pdf"), "en");
        assert_eq!(infer_language_from_path("EP1234567.pdf"), "en");
        assert_eq!(infer_language_from_path("WO2024.pdf"), "en");
        assert_eq!(infer_language_from_path("CN123.pdf"), "ch");
        assert_eq!(infer_language_from_path("random.pdf"), "ch");
    }

    #[test]
    fn test_scanned_pdf_options_ocr_enabled() {
        let opts = scanned_pdf_options("random.pdf");
        assert!(opts.is_ocr, "scanned PDF options must enable OCR");
        assert_eq!(opts.model_version, "vlm");
    }
}

