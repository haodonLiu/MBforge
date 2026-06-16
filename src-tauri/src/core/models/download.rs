//! ModelScope 模型下载（Rust 原生）
//!
//! 使用 reqwest 流式下载，支持进度回调。
//! 替代 Python sidecar 的 download.py。

use super::catalog::*;
use futures::StreamExt;
use std::path::PathBuf;
use tokio::sync::mpsc;

/// 下载进度事件
#[derive(Debug, Clone, serde::Serialize)]
pub struct DownloadProgress {
    pub status: String,     // "connecting" | "downloading" | "completed" | "failed"
    pub file: String,       // 当前文件名
    pub file_progress: f64, // 当前文件进度 0.0-1.0
    pub file_index: usize,  // 当前文件序号
    pub total_files: usize, // 总文件数
    pub error: String,      // 错误信息（仅 failed 时非空）
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
pub async fn download_model(
    resource_id: &str,
    progress_tx: mpsc::Sender<DownloadProgress>,
) -> Result<PathBuf, DownloadError> {
    log::info!("[download_model {}] start", resource_id);
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
        .send(DownloadProgress {
            status: "connecting".into(),
            file: String::new(),
            file_progress: 0.0,
            file_index: 0,
            total_files: 0,
            error: String::new(),
        })
        .await;

    log::info!("[download_model {}] download_type: {}", resource_id, info.download_type);
    let result = if info.download_type == "snapshot" {
        download_snapshot(info, &cache_dir, &progress_tx).await
    } else {
        download_single_file(info, &cache_dir, &progress_tx).await
    };
    match &result {
        Ok(p) => log::info!("[download_model {}] success: {}", resource_id, p.display()),
        Err(e) => {
            log::error!("[download_model {}] error: {}", resource_id, e);
            let _ = progress_tx
                .send(DownloadProgress {
                    status: "failed".into(),
                    file: String::new(),
                    file_progress: 0.0,
                    file_index: 0,
                    total_files: 0,
                    error: e.to_string(),
                })
                .await;
        }
    }
    result
}

/// 下载 snapshot 类型模型（多文件目录）
async fn download_snapshot(
    info: &ResourceInfo,
    cache_dir: &PathBuf,
    progress_tx: &mpsc::Sender<DownloadProgress>,
) -> Result<PathBuf, DownloadError> {
    let repo_name = info.ms_repo.split('/').last().unwrap_or(info.ms_repo);
    let dest = cache_dir.join(repo_name);
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
    let tree_url = format!(
        "https://www.modelscope.cn/api/v1/models/{}/repo/files?Revision=master&Recursive=false",
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

    // 2. 过滤必要文件（支持 allow_patterns）
    let essential: Vec<&str> = files
        .iter()
        .filter_map(|f| f["Path"].as_str().or_else(|| f["path"].as_str()))
        .filter(|p| {
            if info.allow_patterns.is_empty() {
                is_essential_file(p)
            } else {
                info.allow_patterns.iter().any(|pat| glob_match(pat, p))
            }
        })
        .collect();

    let total = essential.len();
    log::info!("[download_snapshot {}] essential files: {:?}", info.id, essential);
    if total == 0 {
        log::error!("[download_snapshot {}] no essential files found", info.id);
        return Err(DownloadError::Api("没有找到可下载的文件".into()));
    }

    // 3. 逐文件下载
    let mut failed_files: Vec<String> = Vec::new();
    for (i, file_path) in essential.iter().enumerate() {
        let _ = progress_tx
            .send(DownloadProgress {
                status: "downloading".into(),
                file: file_path.to_string(),
                file_progress: 0.0,
                file_index: i,
                total_files: total,
                error: String::new(),
            })
            .await;

        let url = format!(
            "https://www.modelscope.cn/{}/resolve/master/{}",
            info.ms_repo, file_path
        );
        log::info!("[download_snapshot {}] [{}/{}] downloading {} from {}", info.id, i + 1, total, file_path, url);

        let resp = client
            .get(&url)
            .send()
            .await
            .map_err(|e| {
                log::error!("[download_snapshot {}] request failed for {}: {}", info.id, file_path, e);
                DownloadError::Network(format!("下载 {} 失败: {}", file_path, e))
            })?;

        if resp.status().is_server_error() || resp.status().is_client_error() {
            log::error!("[download_snapshot {}] HTTP error for {}: {}", info.id, file_path, resp.status());
            failed_files.push(file_path.to_string());
            let _ = progress_tx
                .send(DownloadProgress {
                    status: "failed".into(),
                    file: file_path.to_string(),
                    file_progress: 0.0,
                    file_index: i,
                    total_files: total,
                    error: format!("HTTP {}", resp.status()),
                })
                .await;
            continue;
        }

        let local_path = dest.join(file_path);
        if let Some(parent) = local_path.parent() {
            std::fs::create_dir_all(parent).map_err(|e| DownloadError::Io(e.to_string()))?;
        }

        // 流式写入 + 节流进度上报，避免大文件（如 1.1GB MolScribe checkpoint）
        // 全部缓冲到内存后再写盘，导致进度条长时间不动 + 内存峰值爆涨。
        let total_size = resp.content_length().unwrap_or(0);
        let mut stream = resp.bytes_stream();
        let mut file =
            std::fs::File::create(&local_path).map_err(|e| DownloadError::Io(e.to_string()))?;

        let mut downloaded: u64 = 0;
        let mut last_report: f64 = 0.0;
        // ModelScope resolve/master 响应无 Content-Length 也无 Transfer-Encoding，
        // 因此 content_length=0 时按字节数节流：每 ~5MB 上报一次，synthetic fraction
        // 在 0.05..0.95 之间递增让进度条视觉上移动，最终由末尾 emit 设为 1.0。
        const UNKNOWN_SIZE_TICK: u64 = 5 * 1024 * 1024;
        let mut last_report_bytes: u64 = 0;
        let mut unknown_tick_index: u32 = 0;
        while let Some(chunk) = stream.next().await {
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
                    .send(DownloadProgress {
                        status: "downloading".into(),
                        file: file_path.to_string(),
                        file_progress: frac,
                        file_index: i,
                        total_files: total,
                        error: String::new(),
                    })
                    .await;
            }
        }
        std::io::Write::flush(&mut file).ok();
        log::info!("[download_snapshot {}] [{}/{}] finished {}", info.id, i + 1, total, file_path);
    }

    if !failed_files.is_empty() {
        let err = format!("以下文件下载失败: {}", failed_files.join(", "));
        log::error!("[download_snapshot {}] {}", info.id, err);
        let _ = progress_tx
            .send(DownloadProgress {
                status: "failed".into(),
                file: String::new(),
                file_progress: 0.0,
                file_index: total,
                total_files: total,
                error: err.clone(),
            })
            .await;
        return Err(DownloadError::Api(err));
    }

    log::info!("[download_snapshot {}] all files downloaded", info.id);
    let _ = progress_tx
        .send(DownloadProgress {
            status: "completed".into(),
            file: String::new(),
            file_progress: 1.0,
            file_index: total,
            total_files: total,
            error: String::new(),
        })
        .await;

    Ok(dest)
}

/// 下载单文件模型
async fn download_single_file(
    info: &ResourceInfo,
    cache_dir: &PathBuf,
    progress_tx: &mpsc::Sender<DownloadProgress>,
) -> Result<PathBuf, DownloadError> {
    let url = format!(
        "https://www.modelscope.cn/api/v1/models/{}/repo?Revision=master&FilePath={}",
        info.ms_repo, info.ms_file
    );

    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(600))
        .build()
        .map_err(|e| DownloadError::Network(e.to_string()))?;

    let resp = client
        .get(&url)
        .send()
        .await
        .map_err(|e| DownloadError::Network(e.to_string()))?;

    let content_type = resp
        .headers()
        .get("content-type")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("");
    if content_type.contains("text/html") {
        return Err(DownloadError::Api("需要登录才能下载".into()));
    }

    let total_size = resp.content_length().unwrap_or(0);
    let mut stream = resp.bytes_stream();

    let local_path = cache_dir.join(&info.local_name);
    if let Some(parent) = local_path.parent() {
        std::fs::create_dir_all(parent).map_err(|e| DownloadError::Io(e.to_string()))?;
    }
    let mut file =
        std::fs::File::create(&local_path).map_err(|e| DownloadError::Io(e.to_string()))?;

    let mut downloaded: u64 = 0;
    let mut last_report: f64 = 0.0;
    while let Some(chunk) = stream.next().await {
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
                .send(DownloadProgress {
                    status: "downloading".into(),
                    file: info.ms_file.to_string(),
                    file_progress: frac,
                    file_index: 0,
                    total_files: 1,
                    error: String::new(),
                })
                .await;
        }
    }
    std::io::Write::flush(&mut file).ok();

    let _ = progress_tx
        .send(DownloadProgress {
            status: "completed".into(),
            file: info.ms_file.to_string(),
            file_progress: 1.0,
            file_index: 1,
            total_files: 1,
            error: String::new(),
        })
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
