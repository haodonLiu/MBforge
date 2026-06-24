//! 资源管理器 — Tauri 命令 facade
//!
//! 实际逻辑已迁移到 `core::models` 模块。
//! 此文件仅保留 Tauri 命令注册和向后兼容的 re-export。

pub use mbforge_infra::models::catalog::*;
pub use mbforge_infra::models::download::{download_model, DownloadProgress};
pub use mbforge_infra::models::status::write_resolved_paths;

use std::collections::HashMap;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};

/// 下载任务管理器：防止同一模型重复下载 + 支持取消。
#[derive(Default)]
pub struct DownloadManagerState {
    /// resource_id -> 取消标志。`true` 表示任务应停止。
    active: Mutex<HashMap<String, Arc<AtomicBool>>>,
}

impl DownloadManagerState {
    /// 尝试为 resource_id 注册一个新的下载任务。
    /// 如果该模型已经在下载中，返回 `Err`。
    pub fn start(&self, resource_id: &str) -> Result<Arc<AtomicBool>, String> {
        let mut active = self.active.lock().map_err(|e| e.to_string())?;
        if active.contains_key(resource_id) {
            return Err(format!("{} 正在下载中", resource_id));
        }
        let flag = Arc::new(AtomicBool::new(false));
        active.insert(resource_id.to_string(), Arc::clone(&flag));
        Ok(flag)
    }

    /// 标记任务结束（成功、失败或取消），从 active 中移除。
    pub fn finish(&self, resource_id: &str) {
        if let Ok(mut active) = self.active.lock() {
            active.remove(resource_id);
        }
    }

    /// 请求取消指定 resource_id 的下载任务。
    pub fn cancel(&self, resource_id: &str) -> Result<(), String> {
        let active = self.active.lock().map_err(|e| e.to_string())?;
        let flag = active.get(resource_id).ok_or_else(|| format!("{} 未在下载中", resource_id))?;
        flag.store(true, Ordering::Relaxed);
        Ok(())
    }
}

// ---------------------------------------------------------------------------
// Tauri Commands
// ---------------------------------------------------------------------------

#[tauri::command]
pub fn resources_check() -> mbforge_infra::models::catalog::EnvironmentReport {
    mbforge_infra::models::status::check_all()
}

#[tauri::command]
pub fn resources_status(resource_id: String) -> mbforge_infra::models::catalog::ResourceStatusResult {
    mbforge_infra::models::resolve::check_resource(&resource_id)
}

#[tauri::command]
pub fn resources_get_model_path(resource_id: String) -> Option<String> {
    mbforge_infra::models::resolve::get_model_path(&resource_id)
        .map(|p| p.to_string_lossy().to_string())
}

#[tauri::command]
pub fn resources_catalog() -> Vec<serde_json::Value> {
    mbforge_infra::models::status::catalog_json()
}

/// 下载模型 — 通过 Tauri 事件推送进度
///
/// 前端监听 `model-download-progress` 事件获取实时进度。
/// 同一模型同时只能有一个下载任务。
#[tauri::command]
pub async fn models_download(
    resource_id: String,
    app: tauri::AppHandle<tauri::Wry>,
    state: tauri::State<'_, DownloadManagerState>,
) -> Result<String, String> {
    use tauri::Emitter;

    log::info!("[models_download {}] command invoked", resource_id);

    // 1. 注册下载任务（防止重复启动）
    let cancelled = match state.start(&resource_id) {
        Ok(flag) => flag,
        Err(e) => {
            log::warn!("[models_download {}] {}", resource_id, e);
            return Err(e);
        }
    };

    let (tx, mut rx) = tokio::sync::mpsc::channel::<DownloadProgress>(32);

    // 后台任务：下载 + 转发进度到 Tauri 事件
    let rid = resource_id.clone();
    let cancelled_clone = Arc::clone(&cancelled);
    let download_task = tokio::spawn(async move {
        log::info!("[models_download {}] spawn download_model", rid);
        let result = download_model(&rid, tx, &cancelled_clone, None).await;
        match &result {
            Ok(path) => {
                log::info!("[models_download {}] download_model succeeded: {}", rid, path.display());
            }
            Err(e) => {
                log::error!("[models_download {}] download_model failed: {}", rid, e);
            }
        }
        result.map(|p| p.to_string_lossy().to_string())
    });

    // 转发进度事件
    let app_events = app.clone();
    let rid_forward = resource_id.clone();
    let forward_task = tokio::spawn(async move {
        log::info!("[models_download {}] start forwarding progress events", rid_forward);
        while let Some(progress) = rx.recv().await {
            log::debug!("[models_download {}] forward progress: {:?}", rid_forward, progress);
            if let Err(e) = app_events.emit("model-download-progress", progress) {
                log::warn!("[models_download {}] emit progress failed: {}", rid_forward, e);
            }
        }
        log::info!("[models_download {}] progress channel closed", rid_forward);
    });

    // 等待下载完成
    let result = download_task
        .await
        .map_err(|e| {
            log::error!("[models_download {}] download_task panicked: {}", resource_id, e);
            format!("Task failed: {}", e)
        })
        .and_then(|r| r.map_err(|e| e.to_string()));
    log::info!("[models_download {}] download_task finished: {:?}", resource_id, result);
    let _ = forward_task.await;

    // 下载成功后刷新 resolved_paths.json，让 Python sidecar 立刻可见
    if result.is_ok() {
        mbforge_infra::models::status::write_resolved_paths();
    }

    // 2. 无论成功失败，都从 active 中移除
    state.finish(&resource_id);
    log::info!("[models_download {}] command returning: {:?}", resource_id, result);
    result
}

/// 取消正在进行的下载任务。
#[tauri::command]
pub fn models_cancel_download(
    resource_id: String,
    state: tauri::State<'_, DownloadManagerState>,
) -> Result<(), String> {
    log::info!("[models_cancel_download {}] requested", resource_id);
    state.cancel(&resource_id)
}

/// 下载多文件资源中的单个子文件（如 MolDetv2 的 doc/ 或 general/）
#[tauri::command]
pub async fn models_download_subfile(
    resource_id: String,
    subpath: String,
    app: tauri::AppHandle<tauri::Wry>,
    state: tauri::State<'_, DownloadManagerState>,
) -> Result<String, String> {
    use tauri::Emitter;

    log::info!("[models_download_subfile {}] {} command invoked", resource_id, subpath);

    let cancelled = match state.start(&resource_id) {
        Ok(flag) => flag,
        Err(e) => {
            log::warn!("[models_download_subfile {}] {}", resource_id, e);
            return Err(e);
        }
    };

    let (tx, mut rx) = tokio::sync::mpsc::channel::<DownloadProgress>(32);

    let rid = resource_id.clone();
    let cancelled_clone = Arc::clone(&cancelled);
    let subpath_clone = subpath.clone();
    let download_task = tokio::spawn(async move {
        let result = download_model(&rid, tx, &cancelled_clone, Some(&subpath_clone)).await;
        result.map(|p| p.to_string_lossy().to_string())
    });

    let app_events = app.clone();
    let forward_task = tokio::spawn(async move {
        while let Some(progress) = rx.recv().await {
            let _ = app_events.emit("model-download-progress", progress);
        }
    });

    let result = download_task
        .await
        .map_err(|e| format!("Task failed: {}", e))
        .and_then(|r| r.map_err(|e| e.to_string()));
    let _ = forward_task.await;

    if result.is_ok() {
        mbforge_infra::models::status::write_resolved_paths();
    }

    state.finish(&resource_id);
    result
}

/// 删除已下载的模型
#[tauri::command]
pub fn models_delete(resource_id: String) -> Result<(), String> {
    use mbforge_infra::models::resolve::ms_repo_dir;
    let info = RESOURCE_CATALOG.iter().find(|r| r.id == resource_id);
    let cache_dir = mbforge_infra::config::constants::model_cache_dir();

    // 收集要删除的候选路径（按优先级），并实际删除存在的那些
    let mut candidates: Vec<std::path::PathBuf> = Vec::new();
    if let Some(info) = info {
        if info.resource_type != ResourceType::Model {
            return Err(format!("{} 不是模型资源", resource_id));
        }
        if info.download_type == "file" {
            candidates.push(cache_dir.join(info.local_name));
        } else {
            // snapshot：先按 info.files 精确定位（moldet_doc/general 共享同 dir，必须按文件删）
            let dest = ms_repo_dir(info);
            for rel in info.files {
                candidates.push(dest.join(rel));
            }
            // 兜底：旧 flat 布局 `<cache>/<repo_name>`（兼容手工放置的旧文件）
            let repo_name = info.ms_repo.split('/').next_back().unwrap_or(info.ms_repo);
            let legacy = cache_dir.join(repo_name);
            if legacy.exists() && !candidates.iter().any(|p| p.starts_with(&legacy)) {
                candidates.push(legacy);
            }
        }
    } else {
        // 未知资源 id：尝试常见布局
        candidates.push(cache_dir.join(format!("{}.pt", resource_id)));
        candidates.push(cache_dir.join(&resource_id));
    }

    // 实际删除存在的文件/目录
    let mut any_removed = false;
    let mut last_err = String::new();
    for path in &candidates {
        if !path.exists() {
            continue;
        }
        let result = if path.is_dir() {
            std::fs::remove_dir_all(path).map_err(|e| format!("删除目录失败: {}", e))
        } else {
            std::fs::remove_file(path).map_err(|e| format!("删除文件失败: {}", e))
        };
        match result {
            Ok(()) => any_removed = true,
            Err(e) => last_err = e,
        }
    }

    if !any_removed {
        let listed = candidates
            .iter()
            .map(|p| p.display().to_string())
            .collect::<Vec<_>>()
            .join(" | ");
        return Err(format!("模型不存在: {}", listed));
    }
    if !last_err.is_empty() {
        return Err(last_err);
    }

    // 刷新 resolved_paths.json
    mbforge_infra::models::status::write_resolved_paths();
    Ok(())
}

/// 删除多文件资源（如 MolDetv2 的 doc/general）中的单个子文件。
///
/// `subpath` 必须是 `info.files` 中声明的相对路径（如 `"doc/moldet_v2_yolo11n_960_doc.pt"`）。
/// 未知 `subpath` 返回错误，避免误删 catalog 之外的文件。
#[tauri::command]
pub fn models_delete_subfile(resource_id: String, subpath: String) -> Result<(), String> {
    use mbforge_infra::models::resolve::ms_repo_dir;

    let info = RESOURCE_CATALOG
        .iter()
        .find(|r| r.id == resource_id)
        .ok_or_else(|| format!("未知资源 id: {}", resource_id))?;
    if info.resource_type != ResourceType::Model {
        return Err(format!("{} 不是模型资源", resource_id));
    }
    // 仅允许删除 catalog 中声明的子文件，防止任意路径删除
    if !info.files.iter().any(|f| *f == subpath) {
        return Err(format!(
            "子文件 {} 不在资源 {} 的文件列表中",
            subpath, resource_id
        ));
    }

    let target = ms_repo_dir(info).join(&subpath);
    if !target.exists() {
        return Err(format!("子文件不存在: {}", target.display()));
    }
    if target.is_dir() {
        std::fs::remove_dir_all(&target)
            .map_err(|e| format!("删除目录失败: {}", e))?;
    } else {
        std::fs::remove_file(&target).map_err(|e| format!("删除文件失败: {}", e))?;
    }

    mbforge_infra::models::status::write_resolved_paths();
    Ok(())
}

/// 测试单个模型：实际加载到内存 + 最小推理，验证文件路径与权重有效性。
/// `subpath` 可选，用于多文件资源（如 moldet 的 doc/ 或 general/）。
/// 返回 `{ok, error, duration_ms}`。
#[tauri::command]
pub async fn models_test(
    resource_id: String,
    subpath: Option<String>,
) -> Result<serde_json::Value, String> {
    use mbforge_infra::config::constants::sidecar_url;
    use mbforge_infra::http::client_120s;

    log::info!(
        "[models_test {}] invoked (subpath={:?})",
        resource_id,
        subpath
    );

    let url = format!("{}/api/v1/test/model", sidecar_url());
    let body = serde_json::json!({
        "resource_id": resource_id,
        "subpath": subpath,
    });

    let resp = client_120s()
        .post(&url)
        .json(&body)
        .send()
        .await
        .map_err(|e| format!("调用 sidecar 失败: {}", e))?;

    let status = resp.status();
    let json: serde_json::Value = resp
        .json()
        .await
        .map_err(|e| format!("解析响应失败: {}", e))?;

    if !status.is_success() {
        return Err(format!("sidecar HTTP {}: {}", status, json));
    }

    log::info!(
        "[models_test {}] result: {}",
        resource_id,
        serde_json::to_string(&json).unwrap_or_default()
    );
    Ok(json)
}

/// 刷新模型路径解析结果（重新扫描并写入 resolved_paths.json）
/// 前端 Environment 页面手动刷新按钮调用此命令。
#[tauri::command]
pub fn refresh_resolved_paths() -> Result<serde_json::Value, String> {
    mbforge_infra::models::status::write_resolved_paths();
    let config_dir = mbforge_infra::config::constants::global_config_dir();
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
    let mbforge = mbforge_infra::config::constants::model_cache_dir();
    let mbforge_exists = mbforge.exists();
    let mbforge_size = if mbforge_exists {
        mbforge_infra::models::resolve::dir_size(&mbforge) as f64 / 1024.0 / 1024.0
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
        mbforge_infra::models::resolve::dir_size(&huggingface) as f64 / 1024.0 / 1024.0
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
        mbforge_infra::models::resolve::dir_size(&modelscope) as f64 / 1024.0 / 1024.0
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
