use serde::{Deserialize, Serialize};

/// MinerU API client — supports both Precise and Agent APIs.
///
/// Precise API: https://mineru.net/api/v4/ (needs Token)
/// Agent API:   https://mineru.net/api/v1/agent/ (no Token, IP rate-limited)
pub struct MineruClient {
    host: String,
    api_key: String,
    client: reqwest::blocking::Client,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MineruResult {
    pub markdown: String,
    pub source: String,
    pub task_id: String,
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

    /// Parse a PDF via URL.
    pub fn parse_url(&self, url: &str) -> Result<MineruResult, String> {
        let task_id = self.submit_url(url)?;
        self.wait_for_completion(&task_id)
    }

    /// Parse a local PDF file.
    pub fn parse_file(&self, file_path: &str) -> Result<MineruResult, String> {
        if self.is_agent() {
            self.parse_file_agent(file_path)
        } else {
            self.parse_file_precise(file_path)
        }
    }

    // ---- Agent API (no token) ----

    fn submit_url_agent(&self, url: &str) -> Result<String, String> {
        let api_url = format!("{}/api/v1/agent/parse/url", self.host);
        let body = serde_json::json!({
            "url": url,
            "language": "ch",
            "enable_table": true,
            "enable_formula": true,
        });

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

    fn parse_file_agent(&self, file_path: &str) -> Result<MineruResult, String> {
        let filename = std::path::Path::new(file_path)
            .file_name()
            .and_then(|n| n.to_str())
            .unwrap_or("document.pdf");

        // Step 1: Get signed upload URL
        let api_url = format!("{}/api/v1/agent/parse/file", self.host);
        let body = serde_json::json!({
            "file_name": filename,
            "language": "ch",
            "enable_table": true,
            "enable_formula": true,
        });

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

    fn submit_url_precise(&self, url: &str) -> Result<String, String> {
        let api_url = format!("{}/api/v4/extract/task", self.host);
        let body = serde_json::json!({
            "url": url,
            "model_version": "vlm",
            "enable_formula": true,
            "enable_table": true,
            "language": "ch",
        });

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

    fn poll_precise(&self, task_id: &str) -> Result<MineruResult, String> {
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
                    // For precise API, download the zip and extract markdown
                    let zip_url = result["data"]["full_zip_url"].as_str().unwrap_or("");
                    let markdown = if !zip_url.is_empty() {
                        self.download_and_extract_markdown(zip_url)?
                    } else {
                        String::new()
                    };
                    return Ok(MineruResult {
                        markdown,
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

    fn download_and_extract_markdown(&self, zip_url: &str) -> Result<String, String> {
        // Download zip to temp file
        let resp = self
            .client
            .get(zip_url)
            .send()
            .map_err(|e| format!("Failed to download zip: {}", e))?;
        let zip_bytes = resp
            .bytes()
            .map_err(|e| format!("Failed to read zip: {}", e))?;

        let tmp_dir = tempfile::tempdir().map_err(|e| format!("Temp dir error: {}", e))?;
        let zip_path = tmp_dir.path().join("result.zip");
        std::fs::write(&zip_path, &zip_bytes).map_err(|e| format!("Failed to write zip: {}", e))?;

        // Extract zip
        let zip_file =
            std::fs::File::open(&zip_path).map_err(|e| format!("Failed to open zip: {}", e))?;
        let mut archive = zip::ZipArchive::new(zip_file)
            .map_err(|e| format!("Failed to read zip archive: {}", e))?;

        // Find full.md in the archive
        for i in 0..archive.len() {
            let entry = archive
                .by_index(i)
                .map_err(|e| format!("Zip entry error: {}", e))?;
            let name = entry.name().to_string();
            if name.ends_with("full.md")
                || name.ends_with("full_markdown.md")
                || name.ends_with(".md")
            {
                let mut content = String::new();
                std::io::Read::read_to_string(&mut std::io::BufReader::new(entry), &mut content)
                    .map_err(|e| format!("Failed to read markdown from zip: {}", e))?;
                return Ok(content);
            }
        }

        Err("No markdown file found in zip".into())
    }

    fn parse_file_precise(&self, file_path: &str) -> Result<MineruResult, String> {
        // For precise API with local files, we need to upload first
        // Use the batch endpoint to get upload URLs
        let filename = std::path::Path::new(file_path)
            .file_name()
            .and_then(|n| n.to_str())
            .unwrap_or("document.pdf");

        let api_url = format!("{}/api/v4/file-urls/batch", self.host);
        let body = serde_json::json!({
            "files": [{"name": filename}],
            "model_version": "vlm",
        });

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
        self.poll_batch(&batch_id)
    }

    fn poll_batch(&self, batch_id: &str) -> Result<MineruResult, String> {
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
                        let markdown = if !zip_url.is_empty() {
                            self.download_and_extract_markdown(zip_url)?
                        } else {
                            String::new()
                        };
                        return Ok(MineruResult {
                            markdown,
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

    fn submit_url(&self, url: &str) -> Result<String, String> {
        if self.is_agent() {
            self.submit_url_agent(url)
        } else {
            self.submit_url_precise(url)
        }
    }

    fn wait_for_completion(&self, task_id: &str) -> Result<MineruResult, String> {
        if self.is_agent() {
            self.poll_agent(task_id)
        } else {
            self.poll_precise(task_id)
        }
    }
}
