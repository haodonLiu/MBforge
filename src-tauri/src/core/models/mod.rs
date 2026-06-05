//! 模型管理 — 资源目录、路径解析、下载、环境检测
//!
//! 替代旧的 `resource_manager.rs`（已精简为 facade）。
//! 单一真相源：所有资源 catalog、路径扫描、下载逻辑在此模块。

pub mod catalog;
pub mod download;
pub mod resolve;
pub mod status;

// 便捷 re-exports
pub use catalog::*;
pub use download::{download_model, DownloadProgress, DownloadError};
pub use resolve::{check_resource, get_model_path};
pub use status::{check_all, write_resolved_paths, catalog_json};
