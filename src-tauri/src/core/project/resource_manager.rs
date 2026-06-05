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
// Tauri Commands（保持原有命令名不变）
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
