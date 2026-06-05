//! ModelScope 模型下载（Rust 原生）
//!
//! 使用 reqwest 流式下载，支持进度回调。
//! 替代 Python sidecar 的 download.py。

use std::path::PathBuf;
use tokio::sync::mpsc;
use super::catalog::*;

/// 下载进度事件
#[derive(Debug, Clone, serde::Serialize)]
pub struct DownloadProgress {
    pub status: String,       // "connecting" | "downloading" | "completed" | "failed"
    pub file: String,         // 当前文件名
    pub file_progress: f64,   // 当前文件进度 0.0-1.0
    pub file_index: usize,    // 当前文件序号
    pub total_files: usize,   // 总文件数
    pub error: String,        // 错误信息（仅 failed 时非空）
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
    let info = RESOURCE_CATALOG.iter().find(|r| r.id == resource_id)
        .ok_or_else(|| DownloadError::NotFound(resource_id.to_string()))?;

    if info.resource_type != ResourceType::Model {
        return Err(DownloadError::NotFound(format!("{} 不是模型资源", resource_id)));
    }

    let cache_dir = crate::core::config::constants::model_cache_dir();
    std::fs::create_dir_all(&cache_dir).map_err(|e| DownloadError::Io(e.to_string()))?;

    // 发送 connecting 状态
    let _ = progress_tx.send(DownloadProgress {
        status: "connecting".into(),
        file: String::new(),
        file_progress: 0.0,
        file_index: 0,
        total_files: 0,
        error: String::new(),
    }).await;

    if info.download_type == "snapshot" {
        download_snapshot(info, &cache_dir, &progress_tx).await
    } else {
        download_single_file(info, &cache_dir, &progress_tx).await
    }
}

/// 下载 snapshot 类型模型（多文件目录）
async fn download_snapshot(
    info: &ResourceInfo,
    cache_dir: &PathBuf,
    progress_tx: &mpsc::Sender<DownloadProgress>,
) -> Result<PathBuf, DownloadError> {
    let repo_name = info.ms_repo.split('/').last().unwrap_or(info.ms_repo);
    let dest = cache_dir.join(repo_name);
    std::fs::create_dir_all(&dest).map_err(|e| DownloadError::Io(e.to_string()))?;

    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(300))
        .build()
        .map_err(|e| DownloadError::Network(e.to_string()))?;

    // 1. 获取文件列表
    let tree_url = format!(
        "https://modelscope.cn/api/v1/models/{}/repo/tree?Revision=master",
        info.ms_repo
    );
    let tree_resp = client.get(&tree_url).send().await
        .map_err(|e| DownloadError::Network(e.to_string()))?;
    let tree_text = tree_resp.text().await
        .map_err(|e| DownloadError::Network(e.to_string()))?;
    let tree_val: serde_json::Value = serde_json::from_str(&tree_text)
        .map_err(|e| DownloadError::Api(format!("JSON 解析失败: {}", e)))?;

    let files = tree_val["Data"].as_array()
        .ok_or_else(|| DownloadError::Api("无法获取文件列表".into()))?;

    // 2. 过滤必要文件
    let essential: Vec<&str> = files.iter()
        .filter_map(|f| f["Path"].as_str())
        .filter(|p| is_essential_file(p))
        .collect();

    let total = essential.len();
    if total == 0 {
        return Err(DownloadError::Api("没有找到可下载的文件".into()));
    }

    // 3. 逐文件下载
    for (i, file_path) in essential.iter().enumerate() {
        let _ = progress_tx.send(DownloadProgress {
            status: "downloading".into(),
            file: file_path.to_string(),
            file_progress: 0.0,
            file_index: i,
            total_files: total,
            error: String::new(),
        }).await;

        let url = format!(
            "https://modelscope.cn/api/v1/models/{}/repo?Revision=master&FilePath={}",
            info.ms_repo, file_path
        );

        let resp = client.get(&url).send().await
            .map_err(|e| DownloadError::Network(format!("下载 {} 失败: {}", file_path, e)))?;

        if resp.status().is_server_error() || resp.status().is_client_error() {
            let _ = progress_tx.send(DownloadProgress {
                status: "failed".into(),
                file: file_path.to_string(),
                file_progress: 0.0,
                file_index: i,
                total_files: total,
                error: format!("HTTP {}", resp.status()),
            }).await;
            continue;
        }

        let local_path = dest.join(file_path);
        if let Some(parent) = local_path.parent() {
            std::fs::create_dir_all(parent).map_err(|e| DownloadError::Io(e.to_string()))?;
        }

        let bytes = resp.bytes().await
            .map_err(|e| DownloadError::Network(format!("读取 {} 失败: {}", file_path, e)))?;
        std::fs::write(&local_path, &bytes).map_err(|e| DownloadError::Io(e.to_string()))?;
    }

    let _ = progress_tx.send(DownloadProgress {
        status: "completed".into(),
        file: String::new(),
        file_progress: 1.0,
        file_index: total,
        total_files: total,
        error: String::new(),
    }).await;

    Ok(dest)
}

/// 下载单文件模型
async fn download_single_file(
    info: &ResourceInfo,
    cache_dir: &PathBuf,
    progress_tx: &mpsc::Sender<DownloadProgress>,
) -> Result<PathBuf, DownloadError> {
    let url = format!(
        "https://modelscope.cn/api/v1/models/{}/repo?Revision=master&FilePath={}",
        info.ms_repo, info.ms_file
    );

    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(600))
        .build()
        .map_err(|e| DownloadError::Network(e.to_string()))?;

    let resp = client.get(&url).send().await
        .map_err(|e| DownloadError::Network(e.to_string()))?;

    let content_type = resp.headers().get("content-type")
        .and_then(|v| v.to_str().ok()).unwrap_or("");
    if content_type.contains("text/html") {
        return Err(DownloadError::Api("需要登录才能下载".into()));
    }

    let bytes = resp.bytes().await
        .map_err(|e| DownloadError::Network(e.to_string()))?;

    let local_path = cache_dir.join(&info.local_name);
    std::fs::write(&local_path, &bytes).map_err(|e| DownloadError::Io(e.to_string()))?;

    let _ = progress_tx.send(DownloadProgress {
        status: "completed".into(),
        file: info.ms_file.to_string(),
        file_progress: 1.0,
        file_index: 1,
        total_files: 1,
        error: String::new(),
    }).await;

    Ok(local_path)
}

/// 判断文件是否是模型必要文件
fn is_essential_file(path: &str) -> bool {
    let lower = path.to_lowercase();
    // 权重文件
    if lower.ends_with(".safetensors") || lower.ends_with(".bin")
        || lower.ends_with(".pt") || lower.ends_with(".pth")
        || lower.ends_with(".onnx") {
        return true;
    }
    // 配置文件
    if lower == "config.json" || lower == "tokenizer.json"
        || lower == "tokenizer_config.json" || lower == "special_tokens_map.json"
        || lower == "vocab.txt" || lower == "merges.txt"
        || lower == "generation_config.json" || lower == "preprocessor_config.json"
        || lower == "added_tokens.json" {
        return true;
    }
    false
}
