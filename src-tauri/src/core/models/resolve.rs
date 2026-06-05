//! 路径解析 — 检查资源是否已下载/安装
use std::path::PathBuf;
use super::catalog::*;

/// 检查单个资源状态
pub fn check_resource(resource_id: &str) -> ResourceStatusResult {
    let info = RESOURCE_CATALOG.iter().find(|r| r.id == resource_id);
    let info = match info {
        Some(i) => i,
        None => {
            return ResourceStatusResult {
                id: resource_id.to_string(),
                name: resource_id.to_string(),
                resource_type: ResourceType::Model,
                status: ResourceStatus::Error,
                error: format!("未知资源: {}", resource_id),
                ..Default::default()
            };
        }
    };

    match info.resource_type {
        ResourceType::Model => {
            if info.download_type == "file" {
                check_model_file(info)
            } else {
                check_model_snapshot(info)
            }
        }
        ResourceType::PythonPackage => check_python_package(info),
        ResourceType::Binary => {
            if resource_id == "pdfium" {
                check_pdfium(info)
            } else {
                not_found(info)
            }
        }
    }
}

/// 获取已下载模型的本地路径
pub fn get_model_path(resource_id: &str) -> Option<PathBuf> {
    let status = check_resource(resource_id);
    if status.status == ResourceStatus::Ready && !status.local_path.is_empty() {
        Some(PathBuf::from(&status.local_path))
    } else {
        None
    }
}

// ─── 内部检查函数 ───────────────────────────────────────────────

fn check_model_snapshot(info: &ResourceInfo) -> ResourceStatusResult {
    let cache = crate::core::config::constants::model_cache_dir();
    let repo_name = info.ms_repo.split('/').last().unwrap_or(info.ms_repo);

    // 1. MBForge 缓存
    for name in &[repo_name, &repo_name.replace('.', "___")] {
        let dir = cache.join(name);
        if let Some(result) = check_dir_for_weights(info, &dir) {
            return result;
        }
    }

    // 2. ModelScope 默认缓存
    if let Some(home) = directories::UserDirs::new().map(|u| u.home_dir().to_path_buf()) {
        let ms_org = info.ms_repo.split('/').next().unwrap_or("Qwen");
        for subdir in &["models", "hub/models"] {
            for name in &[repo_name, &repo_name.replace('.', "___")] {
                let dir = home.join(".cache").join("modelscope").join(subdir).join(ms_org).join(name);
                if let Some(result) = check_dir_for_weights(info, &dir) {
                    return result;
                }
            }
        }
    }

    // 3. 环境变量 MODELSCOPE_CACHE
    if let Ok(ms_cache) = std::env::var("MODELSCOPE_CACHE") {
        let ms_org = info.ms_repo.split('/').next().unwrap_or("Qwen");
        for name in &[repo_name, &repo_name.replace('.', "___")] {
            let dir = PathBuf::from(&ms_cache).join(ms_org).join(name);
            if let Some(result) = check_dir_for_weights(info, &dir) {
                return result;
            }
        }
    }

    // 4. HF_HOME
    if let Ok(hf_home) = std::env::var("HF_HOME") {
        let hf_hub = PathBuf::from(&hf_home).join("hub");
        let encoded_name = format!("models--{}", info.ms_repo.replace('/', "--"));
        let snapshots = hf_hub.join(&encoded_name).join("snapshots");
        if snapshots.exists() {
            if let Ok(entries) = std::fs::read_dir(&snapshots) {
                for entry in entries.flatten() {
                    if entry.path().is_dir() {
                        if let Some(result) = check_dir_for_weights(info, &entry.path()) {
                            return result;
                        }
                    }
                }
            }
        }
        let direct = PathBuf::from(&hf_home).join(repo_name);
        if let Some(result) = check_dir_for_weights(info, &direct) {
            return result;
        }
    }

    not_found(info)
}

fn check_dir_for_weights(info: &ResourceInfo, dir: &std::path::Path) -> Option<ResourceStatusResult> {
    if !dir.exists() {
        return None;
    }
    if !has_file_with_ext(dir, &["bin", "safetensors", "pt", "pth", "onnx"]) {
        return None;
    }
    let size = dir_size(dir);
    Some(ResourceStatusResult {
        id: info.id.to_string(),
        name: info.name.to_string(),
        resource_type: info.resource_type.clone(),
        status: ResourceStatus::Ready,
        local_path: dir.to_string_lossy().to_string(),
        size_mb: (size as f64) / 1024.0 / 1024.0,
        version: String::new(),
        error: String::new(),
    })
}

fn check_model_file(info: &ResourceInfo) -> ResourceStatusResult {
    let cache = crate::core::config::constants::model_cache_dir();
    let local_name = if info.local_name.is_empty() {
        format!("{}.pt", info.id)
    } else {
        info.local_name.to_string()
    };

    let path = cache.join(&local_name);
    if path.exists() && path.metadata().map(|m| m.len() > 0).unwrap_or(false) {
        let size = path.metadata().map(|m| m.len()).unwrap_or(0);
        return ResourceStatusResult {
            id: info.id.to_string(),
            name: info.name.to_string(),
            resource_type: info.resource_type.clone(),
            status: ResourceStatus::Ready,
            local_path: path.to_string_lossy().to_string(),
            size_mb: (size as f64) / 1024.0 / 1024.0,
            version: String::new(),
            error: String::new(),
        };
    }

    let repo_name = info.ms_repo.split('/').last().unwrap_or(info.ms_repo);
    let subdir = cache.join(repo_name);
    if subdir.exists() {
        for entry in std::fs::read_dir(&subdir).into_iter().flatten().flatten() {
            let p = entry.path();
            if p.is_file() {
                if let Some(ext) = p.extension().and_then(|e| e.to_str()) {
                    if matches!(ext, "pt" | "pth" | "onnx") {
                        let size = p.metadata().map(|m| m.len()).unwrap_or(0);
                        return ResourceStatusResult {
                            id: info.id.to_string(),
                            name: info.name.to_string(),
                            resource_type: info.resource_type.clone(),
                            status: ResourceStatus::Ready,
                            local_path: p.to_string_lossy().to_string(),
                            size_mb: (size as f64) / 1024.0 / 1024.0,
                            version: String::new(),
                            error: String::new(),
                        };
                    }
                }
            }
        }
    }

    not_found(info)
}

fn check_python_package(info: &ResourceInfo) -> ResourceStatusResult {
    let import_name = if info.import_name.is_empty() { info.pip_name } else { info.import_name };
    let cmd_code = format!("import {}; print(getattr({}, '__version__', ''))", import_name, import_name);

    let output = ["python", "python3"].iter().find_map(|py| {
        std::process::Command::new(py)
            .args(["-c", &cmd_code])
            .stdout(std::process::Stdio::piped())
            .stderr(std::process::Stdio::null())
            .output()
            .ok()
            .filter(|o| o.status.success())
    });

    match output {
        Some(out) => {
            let version = String::from_utf8_lossy(&out.stdout).trim().to_string();
            ResourceStatusResult {
                id: info.id.to_string(),
                name: info.name.to_string(),
                resource_type: info.resource_type.clone(),
                status: ResourceStatus::Ready,
                local_path: String::new(),
                size_mb: 0.0,
                version,
                error: String::new(),
            }
        }
        _ => not_found(info),
    }
}

fn check_pdfium(info: &ResourceInfo) -> ResourceStatusResult {
    if let Ok(manifest) = std::env::var("CARGO_MANIFEST_DIR") {
        let pdfium_lib = PathBuf::from(manifest).join("vendor/pdfium/release/lib");
        if pdfium_lib.exists() && std::fs::read_dir(&pdfium_lib).map(|mut d| d.next().is_some()).unwrap_or(false) {
            return ResourceStatusResult {
                id: info.id.to_string(),
                name: info.name.to_string(),
                resource_type: info.resource_type.clone(),
                status: ResourceStatus::Ready,
                local_path: pdfium_lib.to_string_lossy().to_string(),
                size_mb: 0.0,
                version: String::new(),
                error: String::new(),
            };
        }
    }
    if let Ok(env_path) = std::env::var("PDFIUM_LIB_PATH") {
        let p = PathBuf::from(&env_path);
        if p.exists() {
            return ResourceStatusResult {
                id: info.id.to_string(),
                name: info.name.to_string(),
                resource_type: info.resource_type.clone(),
                status: ResourceStatus::Ready,
                local_path: env_path,
                size_mb: 0.0,
                version: String::new(),
                error: String::new(),
            };
        }
    }
    not_found(info)
}

// ─── 工具函数 ───────────────────────────────────────────────────

fn not_found(info: &ResourceInfo) -> ResourceStatusResult {
    ResourceStatusResult {
        id: info.id.to_string(),
        name: info.name.to_string(),
        resource_type: info.resource_type.clone(),
        status: ResourceStatus::NotFound,
        local_path: String::new(),
        size_mb: 0.0,
        version: String::new(),
        error: String::new(),
    }
}

fn has_file_with_ext(dir: &std::path::Path, exts: &[&str]) -> bool {
    if !dir.is_dir() { return false; }
    walk_dir_for_ext(dir, exts, 3)
}

fn walk_dir_for_ext(dir: &std::path::Path, exts: &[&str], depth: u32) -> bool {
    if depth == 0 { return false; }
    let entries = match std::fs::read_dir(dir) { Ok(e) => e, Err(_) => return false };
    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_file() {
            if let Some(ext) = path.extension().and_then(|e| e.to_str()) {
                if exts.contains(&ext) { return true; }
            }
        } else if path.is_dir() && walk_dir_for_ext(&path, exts, depth - 1) {
            return true;
        }
    }
    false
}

pub fn dir_size(dir: &std::path::Path) -> u64 {
    let mut total = 0u64;
    for entry in walkdir::WalkDir::new(dir).follow_links(false).into_iter().flatten() {
        if entry.file_type().is_file() {
            total += entry.metadata().map(|m| m.len()).unwrap_or(0);
        }
    }
    total
}
