//! 扩展设置命令 — 缓存大小/清除、最近项目增删。

use std::path::{Path, PathBuf};

use mbforge_domain::document::detection_cache::DetectionCache;
use mbforge_domain::document::semantic_cache::SemanticCache;
use mbforge_infra::config::constants::global_data_dir;
use mbforge_infra::config::settings::AppConfig;
use mbforge_infra::models::resolve::dir_size;

// ─── 缓存大小与清除 ─────────────────────────────────────────────

/// 单类缓存大小（MB）
#[derive(serde::Serialize)]
pub struct CacheSize {
    pub semantic_mb: f64,
    pub detection_mb: f64,
    pub molecules_mb: f64,
}

/// 清除结果
#[derive(serde::Serialize)]
pub struct ClearResult {
    pub cache: String,
    pub freed_mb: f64,
    pub success: bool,
    pub error: String,
}

/// 获取项目三类缓存的大小
#[tauri::command]
pub fn cache_size(project_root: String) -> CacheSize {
    let root = PathBuf::from(&project_root);
    CacheSize {
        semantic_mb: size_mb(&project_path(&root, "semantic_cache")),
        detection_mb: size_mb(&project_path(&root, "detection_cache")),
        molecules_mb: size_mb(&project_path(&root, "molecules.db")),
    }
}

fn project_path(root: &Path, name: &str) -> PathBuf {
    // 项目内部缓存：<root>/.mbforge/<name>
    let p = root.join(".mbforge").join(name);
    if p.exists() {
        return p;
    }
    // 全局回退：data_dir/cache/<name>
    global_data_dir().join("cache").join(name)
}

fn size_mb(p: &Path) -> f64 {
    if !p.exists() {
        return 0.0;
    }
    dir_size(p) as f64 / 1024.0 / 1024.0
}

/// 清除指定类型的项目缓存
#[tauri::command]
pub async fn cache_clear(project_root: String, cache: String) -> ClearResult {
    let root = PathBuf::from(&project_root);
    let target = match cache.as_str() {
        "semantic" => project_path(&root, "semantic_cache"),
        "detection" => project_path(&root, "detection_cache"),
        "molecules" => project_path(&root, "molecules.db"),
        other => {
            return ClearResult {
                cache: other.into(),
                freed_mb: 0.0,
                success: false,
                error: format!("未知缓存类型: {}", other),
            };
        }
    };
    let before = size_mb(&target);
    let result = match cache.as_str() {
        "semantic" => clear_semantic(&root).await,
        "detection" => clear_detection(&root),
        "molecules" => clear_molecules(&root),
        _ => unreachable!(),
    };
    let after = size_mb(&target);
    match result {
        Ok(()) => ClearResult {
            cache,
            freed_mb: before - after,
            success: true,
            error: String::new(),
        },
        Err(e) => ClearResult {
            cache,
            freed_mb: 0.0,
            success: false,
            error: e,
        },
    }
}

async fn clear_semantic(root: &Path) -> Result<(), String> {
    let cache = SemanticCache::new(root, Default::default());
    cache.clear().await;
    Ok(())
}

fn clear_detection(root: &Path) -> Result<(), String> {
    let cache = DetectionCache::new(root);
    cache.clear_all().map_err(|e| e.to_string())
}

fn clear_molecules(root: &Path) -> Result<(), String> {
    // 直接删 SQLite 文件；下次访问会由 molecule_store 重新建库
    let db_path = project_path(root, "molecules.db");
    if db_path.is_file() {
        std::fs::remove_file(&db_path).map_err(|e| format!("删除分子库失败: {}", e))?;
    } else if db_path.is_dir() {
        std::fs::remove_dir_all(&db_path).map_err(|e| format!("删除分子库失败: {}", e))?;
    }
    Ok(())
}

// ─── 最近项目 ────────────────────────────────────────────────────

#[derive(serde::Serialize)]
pub struct RecentProjectsResult {
    pub projects: Vec<String>,
}

#[tauri::command]
pub fn projects_list_recent() -> RecentProjectsResult {
    let cfg = AppConfig::load();
    RecentProjectsResult {
        projects: cfg.recent_projects,
    }
}

/// 把路径加入最近项目（去重 + 截断到 8 条 + 前置）
#[tauri::command]
pub fn projects_add_recent(path: String) -> RecentProjectsResult {
    let mut cfg = AppConfig::load();
    cfg.recent_projects.retain(|p| p != &path);
    cfg.recent_projects.insert(0, path);
    cfg.recent_projects.truncate(8);
    let _ = cfg.save();
    RecentProjectsResult {
        projects: cfg.recent_projects,
    }
}

#[tauri::command]
pub fn projects_remove_recent(path: String) -> RecentProjectsResult {
    let mut cfg = AppConfig::load();
    cfg.recent_projects.retain(|p| p != &path);
    let _ = cfg.save();
    RecentProjectsResult {
        projects: cfg.recent_projects,
    }
}

#[tauri::command]
pub fn projects_clear_recent() -> RecentProjectsResult {
    let mut cfg = AppConfig::load();
    cfg.recent_projects.clear();
    let _ = cfg.save();
    RecentProjectsResult { projects: vec![] }
}
