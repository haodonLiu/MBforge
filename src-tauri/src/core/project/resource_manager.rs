//! 资源管理器 — Tauri 命令 facade
//!
//! 实际逻辑已迁移到 `core::models` 模块。
//! 此文件仅保留 Tauri 命令注册和向后兼容的 re-export。

pub use crate::core::models::catalog::*;
pub use crate::core::models::resolve::{check_resource, get_model_path, dir_size};
pub use crate::core::models::status::{check_all as check_all_resources, write_resolved_paths, catalog_json};
pub use crate::core::models::download::{download_model, DownloadProgress, DownloadError};
pub use crate::core::config::constants::model_cache_dir;

// ---------------------------------------------------------------------------
// Tauri Commands
// ---------------------------------------------------------------------------

#[tauri::command]
pub fn resources_check() -> crate::core::models::catalog::EnvironmentReport {
    crate::core::models::status::check_all()
}

#[tauri::command]
pub fn resources_status(resource_id: String) -> crate::core::models::catalog::ResourceStatusResult {
    crate::core::models::resolve::check_resource(&resource_id)
}

#[tauri::command]
pub fn resources_get_model_path(resource_id: String) -> Option<String> {
    crate::core::models::resolve::get_model_path(&resource_id).map(|p| p.to_string_lossy().to_string())
}

#[tauri::command]
pub fn resources_catalog() -> Vec<serde_json::Value> {
    crate::core::models::status::catalog_json()
}

/// 下载模型 — 通过 Tauri 事件推送进度
///
/// 前端监听 `model-download-progress` 事件获取实时进度。
#[tauri::command]
pub async fn models_download(
    resource_id: String,
    app: tauri::AppHandle,
) -> Result<String, String> {
    use tauri::Emitter;

    let (tx, mut rx) = tokio::sync::mpsc::channel::<DownloadProgress>(32);

    // 后台任务：下载 + 转发进度到 Tauri 事件
    let app_clone = app.clone();
    let rid = resource_id.clone();
    let download_task = tokio::spawn(async move {
        let result = download_model(&rid, tx).await;
        match result {
            Ok(path) => {
                let _ = app_clone.emit("model-download-progress", DownloadProgress {
                    status: "completed".into(),
                    file: String::new(),
                    file_progress: 1.0,
                    file_index: 0,
                    total_files: 0,
                    error: String::new(),
                });
                Ok(path.to_string_lossy().to_string())
            }
            Err(e) => {
                let _ = app_clone.emit("model-download-progress", DownloadProgress {
                    status: "failed".into(),
                    file: String::new(),
                    file_progress: 0.0,
                    file_index: 0,
                    total_files: 0,
                    error: e.to_string(),
                });
                Err(e.to_string())
            }
        }
    });

    // 转发进度事件
    let app_events = app.clone();
    let forward_task = tokio::spawn(async move {
        while let Some(progress) = rx.recv().await {
            let _ = app_events.emit("model-download-progress", progress);
        }
    });

    // 等待下载完成
    let result = download_task.await.unwrap_or_else(|e| Err(format!("Task failed: {}", e)));
    let _ = forward_task.await;
    result
}

/// 取消下载（预留接口）
#[tauri::command]
pub fn models_cancel_download(_resource_id: String) -> Result<(), String> {
    // TODO: 实现下载取消逻辑
    Ok(())
}
