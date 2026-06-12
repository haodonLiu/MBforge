//! 扩展设置命令 — 缓存大小/清除、最近项目增删。

use std::path::{Path, PathBuf};

use crate::core::config::constants::global_data_dir;
use crate::core::config::settings::AppConfig;
use crate::core::document::detection_cache::DetectionCache;
use crate::core::document::semantic_cache::SemanticCache;
use crate::core::models::resolve::dir_size;

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
    if !p.exists() { return 0.0; }
    dir_size(p) as f64 / 1024.0 / 1024.0
}

/// 清除指定类型的项目缓存
#[tauri::command]
pub fn cache_clear(project_root: String, cache: String) -> ClearResult {
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
        "semantic" => clear_semantic(&root),
        "detection" => clear_detection(&root),
        "molecules" => clear_molecules(&root),
        _ => unreachable!(),
    };
    let after = size_mb(&target);
    match result {
        Ok(()) => ClearResult { cache, freed_mb: before - after, success: true, error: String::new() },
        Err(e) => ClearResult { cache, freed_mb: 0.0, success: false, error: e },
    }
}

fn clear_semantic(root: &Path) -> Result<(), String> {
    let cache = SemanticCache::new(root, Default::default());
    cache.clear();
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

// ─── 缓存迁移（统一到 ~/.cache/mbforge/models/） ─────────────────

#[derive(serde::Serialize)]
pub struct ConsolidateResult {
    pub model_id: String,
    pub from: String,
    pub to: String,
    pub files_copied: usize,
    pub already_present: bool,
    pub success: bool,
    pub error: String,
}

/// 把 HF / ModelScope 散落的模型迁移到 ~/.cache/mbforge/models/（统一缓存）
#[tauri::command]
pub fn consolidate_models() -> Vec<ConsolidateResult> {
    use crate::core::config::constants::model_cache_dir;
    use crate::core::models::catalog::{RESOURCE_CATALOG, ResourceType};

    let dest_root = model_cache_dir();
    let mut results = Vec::new();

    for info in RESOURCE_CATALOG {
        if info.resource_type != ResourceType::Model {
            continue;
        }
        if info.download_type != "snapshot" {
            continue;  // file 类型已经在 mbforge cache，不需迁移
        }
        let repo_name = info.ms_repo.split('/').last().unwrap_or(info.ms_repo);

        // 1. 已经在目标位置？跳过
        let dest = dest_root.join(repo_name);
        if dest.exists() && std::fs::read_dir(&dest).map(|mut d| d.next().is_some()).unwrap_or(false) {
            results.push(ConsolidateResult {
                model_id: info.id.into(),
                from: String::new(),
                to: dest.to_string_lossy().to_string(),
                files_copied: 0,
                already_present: true,
                success: true,
                error: String::new(),
            });
            continue;
        }

        // 2. 在候选源（ModelScope / HF_HOME）寻找
        let home = std::env::var_os("HOME")
            .or_else(|| std::env::var_os("USERPROFILE"))
            .map(std::path::PathBuf::from);
        let Some(home) = home else { continue };

        // ModelScope 新 SDK 布局：<home>/.cache/modelscope/hub/<org>/<repo>
        let ms_repo_dir = home
            .join(".cache")
            .join("modelscope")
            .join("hub")
            .join(info.ms_repo.split('/').next().unwrap_or(""))
            .join(info.ms_repo.replace('.', "___"));
        // 老 SDK 布局
        let ms_old = home.join(".cache").join("modelscope").join(repo_name);
        // HF 布局
        let hf_repo = home
            .join(".cache")
            .join("huggingface")
            .join("hub")
            .join(format!("models--{}", info.ms_repo.replace('/', "--")));

        let source = [ms_repo_dir, ms_old, hf_repo]
            .into_iter()
            .find(|p| p.exists());

        let Some(src) = source else { continue };

        // 3. 复制
        std::fs::create_dir_all(&dest).ok();
        let mut count = 0usize;
        let mut last_err = String::new();
        if let Ok(entries) = std::fs::read_dir(&src) {
            for entry in entries.flatten() {
                let from = entry.path();
                let to = dest.join(entry.file_name());
                if to.exists() { continue; }
                let r = if from.is_dir() {
                    copy_dir_recursive(&from, &to)
                } else {
                    std::fs::copy(&from, &to).map(|_| ()).map_err(|e| e.to_string())
                };
                match r {
                    Ok(()) => count += 1,
                    Err(e) => last_err = e,
                }
            }
        }
        results.push(ConsolidateResult {
            model_id: info.id.into(),
            from: src.to_string_lossy().to_string(),
            to: dest.to_string_lossy().to_string(),
            files_copied: count,
            already_present: false,
            success: count > 0,
            error: last_err,
        });
    }

    // 触发一次路径解析刷新
    crate::core::models::status::write_resolved_paths();
    results
}

fn copy_dir_recursive(src: &std::path::Path, dst: &std::path::Path) -> Result<(), String> {
    std::fs::create_dir_all(dst).map_err(|e| e.to_string())?;
    for entry in std::fs::read_dir(src).map_err(|e| e.to_string())?.flatten() {
        let from = entry.path();
        let to = dst.join(entry.file_name());
        if from.is_dir() {
            copy_dir_recursive(&from, &to)?;
        } else {
            std::fs::copy(&from, &to).map_err(|e| e.to_string())?;
        }
    }
    Ok(())
}

#[derive(serde::Serialize)]
pub struct RecentProjectsResult {
    pub projects: Vec<String>,
}

#[tauri::command]
pub fn projects_list_recent() -> RecentProjectsResult {
    let cfg = AppConfig::load();
    RecentProjectsResult { projects: cfg.recent_projects }
}

/// 把路径加入最近项目（去重 + 截断到 8 条 + 前置）
#[tauri::command]
pub fn projects_add_recent(path: String) -> RecentProjectsResult {
    let mut cfg = AppConfig::load();
    cfg.recent_projects.retain(|p| p != &path);
    cfg.recent_projects.insert(0, path);
    cfg.recent_projects.truncate(8);
    let _ = cfg.save();
    RecentProjectsResult { projects: cfg.recent_projects }
}

#[tauri::command]
pub fn projects_remove_recent(path: String) -> RecentProjectsResult {
    let mut cfg = AppConfig::load();
    cfg.recent_projects.retain(|p| p != &path);
    let _ = cfg.save();
    RecentProjectsResult { projects: cfg.recent_projects }
}

#[tauri::command]
pub fn projects_clear_recent() -> RecentProjectsResult {
    let mut cfg = AppConfig::load();
    cfg.recent_projects.clear();
    let _ = cfg.save();
    RecentProjectsResult { projects: vec![] }
}
