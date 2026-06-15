//! 资源管理器 — Tauri 命令 facade
//!
//! 实际逻辑已迁移到 `core::models` 模块。
//! 此文件仅保留 Tauri 命令注册和向后兼容的 re-export。

pub use crate::core::models::catalog::*;
pub use crate::core::models::download::{download_model, DownloadProgress};
pub use crate::core::models::status::write_resolved_paths;

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
    crate::core::models::resolve::get_model_path(&resource_id)
        .map(|p| p.to_string_lossy().to_string())
}

#[tauri::command]
pub fn resources_catalog() -> Vec<serde_json::Value> {
    crate::core::models::status::catalog_json()
}

/// 下载模型 — 通过 Tauri 事件推送进度
///
/// 前端监听 `model-download-progress` 事件获取实时进度。
#[tauri::command]
pub async fn models_download(resource_id: String, app: tauri::AppHandle) -> Result<String, String> {
    use tauri::Emitter;

    let (tx, mut rx) = tokio::sync::mpsc::channel::<DownloadProgress>(32);

    // 后台任务：下载 + 转发进度到 Tauri 事件
    let app_clone = app.clone();
    let rid = resource_id.clone();
    let download_task = tokio::spawn(async move {
        let result = download_model(&rid, tx).await;
        match result {
            Ok(path) => {
                let _ = app_clone.emit(
                    "model-download-progress",
                    DownloadProgress {
                        status: "completed".into(),
                        file: String::new(),
                        file_progress: 1.0,
                        file_index: 0,
                        total_files: 0,
                        error: String::new(),
                    },
                );
                Ok(path.to_string_lossy().to_string())
            }
            Err(e) => {
                let _ = app_clone.emit(
                    "model-download-progress",
                    DownloadProgress {
                        status: "failed".into(),
                        file: String::new(),
                        file_progress: 0.0,
                        file_index: 0,
                        total_files: 0,
                        error: e.to_string(),
                    },
                );
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
    let result = download_task
        .await
        .unwrap_or_else(|e| Err(format!("Task failed: {}", e)));
    let _ = forward_task.await;
    result
}

/// 取消下载（预留接口）
#[tauri::command]
pub fn models_cancel_download(_resource_id: String) -> Result<(), String> {
    // TODO: 实现下载取消逻辑
    Ok(())
}

/// 删除已下载的模型
#[tauri::command]
pub fn models_delete(resource_id: String) -> Result<(), String> {
    let info = RESOURCE_CATALOG.iter().find(|r| r.id == resource_id);
    let cache_dir = crate::core::config::constants::model_cache_dir();

    let target = if let Some(info) = info {
        if info.resource_type != ResourceType::Model {
            return Err(format!("{} 不是模型资源", resource_id));
        }
        if info.download_type == "file" {
            cache_dir.join(&info.local_name)
        } else {
            cache_dir.join(info.ms_repo.split('/').last().unwrap_or(info.ms_repo))
        }
    } else {
        let file_target = cache_dir.join(format!("{}.pt", resource_id));
        if file_target.exists() {
            file_target
        } else {
            cache_dir.join(&resource_id)
        }
    };

    if !target.exists() {
        return Err(format!("模型不存在: {}", target.display()));
    }

    if target.is_dir() {
        std::fs::remove_dir_all(&target).map_err(|e| format!("删除目录失败: {}", e))?;
    } else {
        std::fs::remove_file(&target).map_err(|e| format!("删除文件失败: {}", e))?;
    }

    Ok(())
}

/// 刷新模型路径解析结果（重新扫描并写入 resolved_paths.json）
/// 前端 Environment 页面手动刷新按钮调用此命令。
#[tauri::command]
pub fn refresh_resolved_paths() -> Result<serde_json::Value, String> {
    crate::core::models::status::write_resolved_paths();
    let config_dir = crate::core::config::constants::global_config_dir();
    let path = config_dir.join("resolved_paths.json");
    let resources: std::collections::HashMap<String, String> = if path.exists() {
        std::fs::read_to_string(&path)
            .ok()
            .and_then(|s| serde_json::from_str(&s).ok())
            .unwrap_or_default()
    } else {
        std::collections::HashMap::new()
    };
    Ok(serde_json::json!({
        "success": true,
        "resources": resources,
    }))
}

/// 获取模型缓存目录信息
#[tauri::command]
pub fn models_cache_dir_info() -> Result<serde_json::Value, String> {
    let mbforge = crate::core::config::constants::model_cache_dir();
    let mbforge_exists = mbforge.exists();
    let mbforge_size = if mbforge_exists {
        crate::core::models::resolve::dir_size(&mbforge) as f64 / 1024.0 / 1024.0
    } else {
        0.0
    };

    let huggingface = std::env::var("HF_HOME")
        .map(std::path::PathBuf::from)
        .unwrap_or_else(|_| {
            directories::UserDirs::new()
                .map(|u| u.home_dir().join(".cache").join("huggingface"))
                .unwrap_or_default()
        });
    let hf_exists = huggingface.exists();
    let hf_size = if hf_exists {
        crate::core::models::resolve::dir_size(&huggingface) as f64 / 1024.0 / 1024.0
    } else {
        0.0
    };

    let modelscope = std::env::var("MODELSCOPE_CACHE")
        .map(std::path::PathBuf::from)
        .unwrap_or_else(|_| {
            directories::UserDirs::new()
                .map(|u| u.home_dir().join(".cache").join("modelscope"))
                .unwrap_or_default()
        });
    let ms_exists = modelscope.exists();
    let ms_size = if ms_exists {
        crate::core::models::resolve::dir_size(&modelscope) as f64 / 1024.0 / 1024.0
    } else {
        0.0
    };

    Ok(serde_json::json!({
        "mbforge": {
            "path": mbforge.to_string_lossy().to_string(),
            "exists": mbforge_exists,
            "size_mb": mbforge_size,
        },
        "huggingface": {
            "path": huggingface.to_string_lossy().to_string(),
            "exists": hf_exists,
            "size_mb": hf_size,
            "env_var": "HF_HOME",
        },
        "modelscope": {
            "path": modelscope.to_string_lossy().to_string(),
            "exists": ms_exists,
            "size_mb": ms_size,
            "env_var": "MODELSCOPE_CACHE",
        },
    }))
}
