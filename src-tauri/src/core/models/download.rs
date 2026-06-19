//! ModelScope 模型下载（Rust 原生）
//!
//! 使用 reqwest 流式下载，支持进度回调。
//! 替代 Python sidecar 的 download.py。

use super::catalog::*;
use futures::StreamExt;
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use tokio::sync::mpsc;

/// 下载进度事件
#[derive(Debug, Clone, serde::Serialize)]
pub struct DownloadProgress {
    pub resource_id: String, // 模型/资源 ID，用于区分同时下载的多个模型
    pub status: String,      // "connecting" | "downloading" | "completed" | "failed"
    pub file: String,        // 当前文件名
    pub file_progress: f64,  // 当前文件进度 0.0-1.0
    pub file_index: usize,   // 当前文件序号
    pub total_files: usize,  // 总文件数
    pub error: String,       // 错误信息（仅 failed 时非空）
}

impl DownloadProgress {
    fn new(resource_id: &str, status: &str) -> Self {
        Self {
            resource_id: resource_id.to_string(),
            status: status.to_string(),
            file: String::new(),
            file_progress: 0.0,
            file_index: 0,
            total_files: 0,
            error: String::new(),
        }
    }

    fn with_file(mut self, file: &str) -> Self {
        self.file = file.to_string();
        self
    }

    fn with_progress(mut self, file_progress: f64) -> Self {
        self.file_progress = file_progress;
        self
    }

    fn with_index(mut self, file_index: usize, total_files: usize) -> Self {
        self.file_index = file_index;
        self.total_files = total_files;
        self
    }

    fn with_error(mut self, error: &str) -> Self {
        self.error = error.to_string();
        self
    }
}

/// 下载错误
#[derive(Debug, thiserror::Error)]
pub enum DownloadError {
    #[error("资源不存在: {0}")]
    NotFound(String),
    #[error("网络错误: {0}")]
    Network(String),
    #[error("IO 错误: {0}")]
    Io(String),
    #[error("API 错误: {0}")]
    Api(String),
}

/// 下载单个模型到本地缓存目录
///
/// 通过 `progress_tx` 推送进度事件，前端可通过 Tauri 事件监听。
/// `subpath_filter`：可选，仅下载 `info.files` 中匹配的子文件（用于多文件资源如 MolDetv2）。
pub async fn download_model(
    resource_id: &str,
    progress_tx: mpsc::Sender<DownloadProgress>,
    cancelled: &Arc<AtomicBool>,
    subpath_filter: Option<&str>,
) -> Result<PathBuf, DownloadError> {
    log::info!("[download_model {}] start (filter={:?})", resource_id, subpath_filter);
    let info = RESOURCE_CATALOG
        .iter()
        .find(|r| r.id == resource_id)
        .ok_or_else(|| DownloadError::NotFound(resource_id.to_string()))?;

    if info.resource_type != ResourceType::Model {
        log::error!("[download_model {}] not a model resource (type {:?})", resource_id, info.resource_type);
        return Err(DownloadError::NotFound(format!(
            "{} 不是模型资源",
            resource_id
        )));
    }

    let cache_dir = crate::core::config::constants::model_cache_dir();
    log::info!("[download_model {}] cache_dir: {}", resource_id, cache_dir.display());
    std::fs::create_dir_all(&cache_dir).map_err(|e| DownloadError::Io(e.to_string()))?;

    // 发送 connecting 状态
    let _ = progress_tx
        .send(DownloadProgress::new(resource_id, "connecting"))
        .await;

    log::info!("[download_model {}] download_type: {}", resource_id, info.download_type);
    let result = if info.download_type == "snapshot" {
        download_snapshot(resource_id, info, &cache_dir, &progress_tx, cancelled, subpath_filter).await
    } else {
        download_single_file(resource_id, info, &cache_dir, &progress_tx, cancelled).await
    };
    match &result {
        Ok(p) => log::info!("[download_model {}] success: {}", resource_id, p.display()),
        Err(e) => {
            log::error!("[download_model {}] error: {}", resource_id, e);
            let _ = progress_tx
                .send(DownloadProgress::new(resource_id, "failed").with_error(&e.to_string()))
                .await;
        }
    }
    result
}

/// 下载 snapshot 类型模型（多文件目录）
/// `subpath_filter`：可选，仅下载 `info.files` 中匹配的子文件
async fn download_snapshot(
    resource_id: &str,
    info: &ResourceInfo,
    cache_dir: &PathBuf,
    progress_tx: &mpsc::Sender<DownloadProgress>,
    cancelled: &Arc<AtomicBool>,
    subpath_filter: Option<&str>,
) -> Result<PathBuf, DownloadError> {
    let repo_name = info.ms_repo.split('/').last().unwrap_or(info.ms_repo);
    let org = info.ms_repo.split('/').next().unwrap_or("");
    // ModelScope SDK 布局: <cache>/<org>/<repo>（repo 中 . 替换为 ___）
    let encoded_repo = repo_name.replace('.', "___");
    let dest = if org.is_empty() {
        cache_dir.join(&encoded_repo)
    } else {
        cache_dir.join(org).join(&encoded_repo)
    };
    log::info!("[download_snapshot {}] dest: {}", info.id, dest.display());
    std::fs::create_dir_all(&dest).map_err(|e| DownloadError::Io(e.to_string()))?;

    let client = reqwest::Client::builder()
        // ModelScope 大文件通过 HTTP/2 传输时偶发中断，强制 HTTP/1.1 更稳定
        .http1_only()
        .user_agent("MBForge/0.2.0 (model-downloader; +https://github.com/mbforge/mbforge)")
        .timeout(std::time::Duration::from_secs(600))
        .build()
        .map_err(|e| DownloadError::Network(e.to_string()))?;

    // 1. 获取文件列表（ModelScope models API 使用 repo/files，不是 repo/tree）
    //    Recursive=true 以便发现子目录文件（如 1_Pooling/config.json）
    let tree_url = format!(
        "https://www.modelscope.cn/api/v1/models/{}/repo/files?Revision=master&Recursive=true",
        info.ms_repo
    );
    log::info!("[download_snapshot {}] fetch file list: {}", info.id, tree_url);
    let tree_resp = client
        .get(&tree_url)
        .send()
        .await
        .map_err(|e| DownloadError::Network(e.to_string()))?;
    let tree_status = tree_resp.status();
    log::info!("[download_snapshot {}] file list response status: {}", info.id, tree_status);
    let tree_text = tree_resp
        .text()
        .await
        .map_err(|e| DownloadError::Network(e.to_string()))?;

    // 检查是否返回了 HTML（登录页/错误页）或非 JSON
    let trimmed = tree_text.trim();
    if trimmed.starts_with('<') || trimmed.starts_with("404") || trimmed.starts_with("50") {
        log::error!("[download_snapshot {}] non-JSON / error response (HTTP {}): {}", info.id, tree_status, &tree_text[..tree_text.len().min(200)]);
        return Err(DownloadError::Api(format!(
            "API 错误 (HTTP {}): {}",
            tree_status,
            &tree_text[..tree_text.len().min(200)]
        )));
    }

    let tree_val: serde_json::Value = serde_json::from_str(&tree_text)
        .map_err(|e| DownloadError::Api(format!("JSON 解析失败: {} | 原文: {}", e, &tree_text[..tree_text.len().min(200)])))?;

    // ModelScope API 返回格式: { "Data": { "Files": [...] } }
    let files = tree_val["Data"]["Files"]
        .as_array()
        .or_else(|| tree_val["Data"].as_array())
        .ok_or_else(|| DownloadError::Api(format!("无法获取文件列表: {:?}", tree_val)))?;

    log::info!("[download_snapshot {}] total entries: {}", info.id, files.len());

    // 2. 选择要下载的文件：
    //    a) 若 info.files 非空（精确文件列表），用列表本身（跳过 API 列表拉取可优化，但保留拉取以便校验）
    //    b) 否则按 allow_patterns 过滤
    //    c) 兜底：通用 is_essential_file
    let owned_paths: Vec<String> = files
        .iter()
        .filter_map(|f| f["Path"].as_str().or_else(|| f["path"].as_str()).map(String::from))
        .collect();
    let essential: Vec<String> = if !info.files.is_empty() {
        // 验证精确列表里的文件实际存在于仓库
        info.files
            .iter()
            .filter(|want| {
                let exists = owned_paths.iter().any(|p| p == *want);
                if !exists {
                    log::warn!("[download_snapshot {}] requested file not in repo: {}", info.id, want);
                }
                exists
            })
            .map(|s| s.to_string())
            .collect()
    } else {
        owned_paths
            .iter()
            .filter(|p| {
                if info.allow_patterns.is_empty() {
                    is_essential_file(p)
                } else {
                    info.allow_patterns.iter().any(|pat| glob_match(pat, p))
                }
            })
            .cloned()
            .collect()
    };

    let total = essential.len();
    log::info!("[download_snapshot {}] essential files: {:?}", info.id, essential);
    if total == 0 {
        log::error!("[download_snapshot {}] no essential files found", info.id);
        return Err(DownloadError::Api("没有找到可下载的文件".into()));
    }

    // 3. 逐文件下载（支持断点续传 + 原子写入 + 取消）
    let mut failed_files: Vec<String> = Vec::new();
    for (i, file_path) in essential.iter().enumerate() {
        if cancelled.load(Ordering::Relaxed) {
            log::info!("[download_snapshot {}] cancelled before {}", resource_id, file_path);
            return Err(DownloadError::Api("下载已取消".into()));
        }

        let _ = progress_tx
            .send(
                DownloadProgress::new(resource_id, "downloading")
                    .with_file(file_path)
                    .with_index(i, total),
            )
            .await;

        let url = format!(
            "https://www.modelscope.cn/{}/resolve/master/{}",
            info.ms_repo, file_path
        );
        log::info!("[download_snapshot {}] [{}/{}] downloading {} from {}", info.id, i + 1, total, file_path, url);

        let local_path = dest.join(file_path);
        let part_path = local_path.with_extension("part");
        if let Some(parent) = local_path.parent() {
            std::fs::create_dir_all(parent).map_err(|e| DownloadError::Io(e.to_string()))?;
        }

        // 已下载的字节数（断点续传）
        let mut existing_size: u64 = 0;
        if part_path.exists() {
            existing_size = std::fs::metadata(&part_path)
                .map(|m| m.len())
                .unwrap_or(0);
            log::info!("[download_snapshot {}] {} resuming from {} bytes", resource_id, file_path, existing_size);
        }

        let mut req = client.get(&url);
        if existing_size > 0 {
            req = req.header("Range", format!("bytes={}-", existing_size));
        }

        let resp = req.send().await.map_err(|e| {
            log::error!("[download_snapshot {}] request failed for {}: {}", info.id, file_path, e);
            DownloadError::Network(format!("下载 {} 失败: {}", file_path, e))
        })?;

        let status = resp.status();
        if status.is_server_error() || (status.is_client_error() && status != reqwest::StatusCode::RANGE_NOT_SATISFIABLE) {
            log::error!("[download_snapshot {}] HTTP error for {}: {}", info.id, file_path, status);
            failed_files.push(file_path.to_string());
            let _ = progress_tx
                .send(
                    DownloadProgress::new(resource_id, "failed")
                        .with_file(file_path)
                        .with_index(i, total)
                        .with_error(&format!("HTTP {}", status)),
                )
                .await;
            continue;
        }

        // 根据响应状态决定如何打开 .part 文件
        let (mut file, effective_existing) = if status == reqwest::StatusCode::PARTIAL_CONTENT {
            // 206 Partial Content：追加到已有 .part 文件
            let file = std::fs::OpenOptions::new()
                .write(true)
                .create(true)
                .append(true)
                .open(&part_path)
                .map_err(|e| DownloadError::Io(e.to_string()))?;
            (file, existing_size)
        } else if status == reqwest::StatusCode::RANGE_NOT_SATISFIABLE {
            // 416：Range 不满足，说明文件已完整，直接重命名
            log::info!("[download_snapshot {}] {} already complete (416)", resource_id, file_path);
            std::fs::rename(&part_path, &local_path).map_err(|e| DownloadError::Io(e.to_string()))?;
            continue;
        } else {
            // 200 OK 或其他：服务器不支持 Range，从头下载
            if existing_size > 0 {
                log::warn!("[download_snapshot {}] {} server ignored Range, restarting", resource_id, file_path);
            }
            let file = std::fs::File::create(&part_path).map_err(|e| DownloadError::Io(e.to_string()))?;
            (file, 0)
        };

        let content_len = resp.content_length();
        let total_size = content_len.map(|c| c + effective_existing).unwrap_or(effective_existing);
        let mut stream = resp.bytes_stream();

        let mut downloaded: u64 = effective_existing;
        let mut last_report: f64 = if total_size > 0 {
            effective_existing as f64 / total_size as f64
        } else {
            0.0
        };
        const UNKNOWN_SIZE_TICK: u64 = 5 * 1024 * 1024;
        let mut last_report_bytes: u64 = effective_existing;
        let mut unknown_tick_index: u32 = (effective_existing / UNKNOWN_SIZE_TICK) as u32;
        while let Some(chunk) = stream.next().await {
            if cancelled.load(Ordering::Relaxed) {
                log::info!("[download_snapshot {}] cancelled during {}", resource_id, file_path);
                return Err(DownloadError::Api("下载已取消".into()));
            }
            let chunk = chunk
                .map_err(|e| DownloadError::Network(format!("读取 {} 失败: {}", file_path, e)))?;
            std::io::Write::write_all(&mut file, &chunk)
                .map_err(|e| DownloadError::Io(e.to_string()))?;
            downloaded += chunk.len() as u64;
            let (frac, should_report) = if total_size > 0 {
                let f = downloaded as f64 / total_size as f64;
                (f, f - last_report > 0.01 || f >= 1.0)
            } else {
                let tick = downloaded - last_report_bytes >= UNKNOWN_SIZE_TICK;
                let f = if tick {
                    unknown_tick_index = unknown_tick_index.saturating_add(1);
                    last_report_bytes = downloaded;
                    (unknown_tick_index as f64 * 0.05).min(0.95)
                } else {
                    last_report
                };
                (f, tick)
            };
            if should_report {
                last_report = frac;
                let _ = progress_tx
                    .send(
                        DownloadProgress::new(resource_id, "downloading")
                            .with_file(file_path)
                            .with_progress(frac)
                            .with_index(i, total),
                    )
                    .await;
            }
        }
        std::io::Write::flush(&mut file).ok();

        // 原子重命名：.part -> 最终文件
        std::fs::rename(&part_path, &local_path).map_err(|e| DownloadError::Io(e.to_string()))?;
        log::info!("[download_snapshot {}] [{}/{}] finished {}", info.id, i + 1, total, file_path);
    }

    if !failed_files.is_empty() {
        let err = format!("以下文件下载失败: {}", failed_files.join(", "));
        log::error!("[download_snapshot {}] {}", info.id, err);
        let _ = progress_tx
            .send(
                DownloadProgress::new(resource_id, "failed")
                    .with_index(total, total)
                    .with_error(&err),
            )
            .await;
        return Err(DownloadError::Api(err));
    }

    log::info!("[download_snapshot {}] all files downloaded", info.id);
    let _ = progress_tx
        .send(
            DownloadProgress::new(resource_id, "completed")
                .with_progress(1.0)
                .with_index(total, total),
        )
        .await;

    Ok(dest)
}

/// 下载单文件模型
async fn download_single_file(
    resource_id: &str,
    info: &ResourceInfo,
    cache_dir: &PathBuf,
    progress_tx: &mpsc::Sender<DownloadProgress>,
    cancelled: &Arc<AtomicBool>,
) -> Result<PathBuf, DownloadError> {
    let url = format!(
        "https://www.modelscope.cn/api/v1/models/{}/repo?Revision=master&FilePath={}",
        info.ms_repo, info.ms_file
    );

    if cancelled.load(Ordering::Relaxed) {
        return Err(DownloadError::Api("下载已取消".into()));
    }

    let local_path = cache_dir.join(&info.local_name);
    let part_path = local_path.with_extension("part");
    if let Some(parent) = local_path.parent() {
        std::fs::create_dir_all(parent).map_err(|e| DownloadError::Io(e.to_string()))?;
    }

    let existing_size: u64 = if part_path.exists() {
        std::fs::metadata(&part_path).map(|m| m.len()).unwrap_or(0)
    } else {
        0
    };

    let client = reqwest::Client::builder()
        .http1_only()
        .user_agent("MBForge/0.2.0 (model-downloader; +https://github.com/mbforge/mbforge)")
        .timeout(std::time::Duration::from_secs(600))
        .build()
        .map_err(|e| DownloadError::Network(e.to_string()))?;

    let mut req = client.get(&url);
    if existing_size > 0 {
        req = req.header("Range", format!("bytes={}-", existing_size));
    }

    let resp = req.send().await.map_err(|e| DownloadError::Network(e.to_string()))?;

    let content_type = resp
        .headers()
        .get("content-type")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("");
    if content_type.contains("text/html") {
        return Err(DownloadError::Api("需要登录才能下载".into()));
    }

    let status = resp.status();
    if status.is_server_error() || (status.is_client_error() && status != reqwest::StatusCode::RANGE_NOT_SATISFIABLE) {
        return Err(DownloadError::Api(format!("HTTP {}", status)));
    }

    // 根据响应状态决定如何打开 .part 文件
    let (mut file, effective_existing) = if status == reqwest::StatusCode::PARTIAL_CONTENT {
        let file = std::fs::OpenOptions::new()
            .write(true)
            .create(true)
            .append(true)
            .open(&part_path)
            .map_err(|e| DownloadError::Io(e.to_string()))?;
        (file, existing_size)
    } else if status == reqwest::StatusCode::RANGE_NOT_SATISFIABLE {
        std::fs::rename(&part_path, &local_path).map_err(|e| DownloadError::Io(e.to_string()))?;
        return Ok(local_path);
    } else {
        let file = std::fs::File::create(&part_path).map_err(|e| DownloadError::Io(e.to_string()))?;
        (file, 0)
    };

    let content_len = resp.content_length();
    let total_size = content_len.map(|c| c + effective_existing).unwrap_or(effective_existing);
    let mut stream = resp.bytes_stream();

    let mut downloaded: u64 = effective_existing;
    let mut last_report: f64 = if total_size > 0 {
        effective_existing as f64 / total_size as f64
    } else {
        0.0
    };
    while let Some(chunk) = stream.next().await {
        if cancelled.load(Ordering::Relaxed) {
            return Err(DownloadError::Api("下载已取消".into()));
        }
        let chunk = chunk.map_err(|e| DownloadError::Network(e.to_string()))?;
        std::io::Write::write_all(&mut file, &chunk)
            .map_err(|e| DownloadError::Io(e.to_string()))?;
        downloaded += chunk.len() as u64;
        let frac = if total_size > 0 {
            downloaded as f64 / total_size as f64
        } else {
            0.0
        };
        // 节流：每 1% 报告一次
        if frac - last_report > 0.01 || frac >= 1.0 {
            last_report = frac;
            let _ = progress_tx
                .send(
                    DownloadProgress::new(resource_id, "downloading")
                        .with_file(&info.ms_file)
                        .with_progress(frac)
                        .with_index(0, 1),
                )
                .await;
        }
    }
    std::io::Write::flush(&mut file).ok();

    // 原子重命名
    std::fs::rename(&part_path, &local_path).map_err(|e| DownloadError::Io(e.to_string()))?;

    let _ = progress_tx
        .send(
            DownloadProgress::new(resource_id, "completed")
                .with_file(&info.ms_file)
                .with_progress(1.0)
                .with_index(1, 1),
        )
        .await;

    Ok(local_path)
}

/// 判断文件是否是模型必要文件
fn is_essential_file(path: &str) -> bool {
    let lower = path.to_lowercase();
    // 权重文件
    if lower.ends_with(".safetensors")
        || lower.ends_with(".bin")
        || lower.ends_with(".pt")
        || lower.ends_with(".pth")
    {
        return true;
    }
    // 配置文件
    if lower == "config.json"
        || lower == "tokenizer.json"
        || lower == "tokenizer_config.json"
        || lower == "special_tokens_map.json"
        || lower == "vocab.txt"
        || lower == "merges.txt"
        || lower == "generation_config.json"
        || lower == "preprocessor_config.json"
        || lower == "added_tokens.json"
    {
        return true;
    }
    false
}

/// 简易 glob 匹配（仅支持 * 通配符）
fn glob_match(pattern: &str, path: &str) -> bool {
    let pat_lower = pattern.to_lowercase();
    let path_lower = path.to_lowercase();
    if pat_lower.contains('*') {
        let parts: Vec<&str> = pat_lower.split('*').collect();
        if parts.len() == 2 {
            let prefix = parts[0];
            let suffix = parts[1];
            path_lower.starts_with(prefix) && path_lower.ends_with(suffix)
        } else {
            path_lower.contains(&pat_lower.replace('*', ""))
        }
    } else {
        path_lower == pat_lower
    }
}
