//! 路径解析 �?检查资源是否已下载/安装
use super::catalog::*;
use std::path::PathBuf;

/// 检查单个资源状�?
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
        ResourceType::Binary => not_found(info),
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

// ─── 内部检查函�?───────────────────────────────────────────────

/// �?ENV 优先级顺序搜�?snapshot 类型模型�?
/// 顺序: MBFORGE_MODEL_CACHE_DIR �?HF_HOME �?MODELSCOPE_CACHE �?TORCH_HOME �?默认回退
fn check_model_snapshot(info: &ResourceInfo) -> ResourceStatusResult {
    let repo_name = info.ms_repo.split('/').last().unwrap_or(info.ms_repo);
    let ms_org = info.ms_repo.split('/').next().unwrap_or("Qwen");

    // 1. MBForge 缓存（env > config > default�?
    let mbforge_cache = crate::core::config::constants::model_cache_dir();
    for name in &[repo_name, &repo_name.replace('.', "___")] {
        let dir = mbforge_cache.join(name);
        if let Some(result) = check_dir_for_weights(info, &dir) {
            return result;
        }
    }

    // 2. HF_HOME
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

    // 3. MODELSCOPE_CACHE（env > default�?
    let ms_cache_candidates = vec![
        std::env::var("MODELSCOPE_CACHE").ok().map(PathBuf::from),
        directories::UserDirs::new().map(|u| u.home_dir().join(".cache").join("modelscope")),
    ];
    for ms_root in ms_cache_candidates.into_iter().flatten() {
        // 覆盖新旧 SDK 布局�?"（早期）/"models"/"hub"（新版扁平）/"hub/models"（旧版嵌套）
        for subdir in &["", "models", "hub", "hub/models"] {
            for name in &[repo_name, &repo_name.replace('.', "___")] {
                let dir = ms_root.join(subdir).join(ms_org).join(name);
                if let Some(result) = check_dir_for_weights(info, &dir) {
                    return result;
                }
            }
        }
    }

    // 4. TORCH_HOME
    if let Ok(torch_home) = std::env::var("TORCH_HOME") {
        for name in &[repo_name, &repo_name.replace('.', "___")] {
            let dir = PathBuf::from(&torch_home).join(name);
            if let Some(result) = check_dir_for_weights(info, &dir) {
                return result;
            }
        }
    }

    not_found(info)
}

fn check_dir_for_weights(
    info: &ResourceInfo,
    dir: &std::path::Path,
) -> Option<ResourceStatusResult> {
    if !dir.exists() {
        return None;
    }
    if !has_file_with_ext(dir, &["bin", "safetensors", "pt", "pth"]) {
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

/// �?ENV 优先级顺序搜索单文件类型模型�?
/// 顺序�?snapshot 一�? MBFORGE_MODEL_CACHE_DIR �?HF_HOME �?MODELSCOPE_CACHE �?TORCH_HOME �?默认回退
fn check_model_file(info: &ResourceInfo) -> ResourceStatusResult {
    let local_name = if info.local_name.is_empty() {
        format!("{}.pt", info.id)
    } else {
        info.local_name.to_string()
    };
    let repo_name = info.ms_repo.split('/').last().unwrap_or(info.ms_repo);

    // local_name �?stem（去扩展名）�?用于子目录名匹配
    let local_stem = std::path::Path::new(&local_name)
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or(&local_name);

    // 在一�?base 目录下查找：精确文件�?�?local_stem 子目�?�?repo_name 子目�?�?递归
    // 关键字过滤：递归 / 子目录扫描出来的文件必须包含模型 id 或 repo 末段，
    // 否则会把别的模型权重误归到本模型（例如 molscribe 查询抓到 moldet 的 .pt）
    let id_key = info.id.to_lowercase();
    let repo_key = info
        .ms_repo
        .split('/')
        .last()
        .unwrap_or(info.ms_repo)
        .to_lowercase();

    let search_base = |base: &std::path::Path| -> Option<ResourceStatusResult> {
        // 1. base/<local_name>（精确文件）
        let path = base.join(&local_name);
        if path.exists() && path.metadata().map(|m| m.len() > 0).unwrap_or(false) {
            let size = path.metadata().map(|m| m.len()).unwrap_or(0);
            return Some(mk_ready(info, &path, size));
        }
        // 2. base/<local_stem>/<local_name>（子目录匹配�?
        let stem_subdir = base.join(local_stem);
        if let Some(p) =
            find_weights_in_dir(&stem_subdir).filter(|p| path_matches(p, &id_key, &repo_key))
        {
            return Some(mk_ready(
                info,
                &p,
                p.metadata().map(|m| m.len()).unwrap_or(0),
            ));
        }
        // 3. base/<repo_name>/<any .pt|.pth>（按 repo 划分的子目录�?
        let subdir = base.join(&repo_name);
        if let Some(p) =
            find_weights_in_dir(&subdir).filter(|p| path_matches(p, &id_key, &repo_key))
        {
            return Some(mk_ready(
                info,
                &p,
                p.metadata().map(|m| m.len()).unwrap_or(0),
            ));
        }
        // 4. 递归扫描 base �?2 层内�?.pt|.pth|.bin|.safetensors（兜底，匹配用户自定义子目录布局�?
        if let Some(p) =
            find_weights_recursive(base, 2).filter(|p| path_matches(p, &id_key, &repo_key))
        {
            return Some(mk_ready(
                info,
                &p,
                p.metadata().map(|m| m.len()).unwrap_or(0),
            ));
        }
        None
    };

    // 1. MBForge 缓存
    if let Some(result) = search_base(&crate::core::config::constants::model_cache_dir()) {
        return result;
    }

    // 2. HF_HOME
    if let Ok(hf_home) = std::env::var("HF_HOME") {
        if let Some(result) = search_base(&PathBuf::from(&hf_home)) {
            return result;
        }
    }

    // 3. MODELSCOPE_CACHE
    if let Ok(ms_cache) = std::env::var("MODELSCOPE_CACHE") {
        if let Some(result) = search_base(&PathBuf::from(&ms_cache)) {
            return result;
        }
    }
    if let Some(home) = directories::UserDirs::new().map(|u| u.home_dir().to_path_buf()) {
        if let Some(result) = search_base(&home.join(".cache").join("modelscope")) {
            return result;
        }
    }

    // 4. TORCH_HOME
    if let Ok(torch_home) = std::env::var("TORCH_HOME") {
        if let Some(result) = search_base(&PathBuf::from(&torch_home)) {
            return result;
        }
    }

    not_found(info)
}

fn check_python_package(info: &ResourceInfo) -> ResourceStatusResult {
    let import_name = if info.import_name.is_empty() {
        info.pip_name
    } else {
        info.import_name
    };
    let cmd_code = format!(
        "import {}; print(getattr({}, '__version__', ''))",
        import_name, import_name
    );

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

fn has_files(p: &std::path::Path) -> bool {
    p.exists()
        && std::fs::read_dir(p)
            .map(|mut d| d.next().is_some())
            .unwrap_or(false)
}

/// 构造一�?Ready 状态结�?
fn mk_ready(info: &ResourceInfo, path: &std::path::Path, size: u64) -> ResourceStatusResult {
    ResourceStatusResult {
        id: info.id.to_string(),
        name: info.name.to_string(),
        resource_type: info.resource_type.clone(),
        status: ResourceStatus::Ready,
        local_path: path.to_string_lossy().to_string(),
        size_mb: (size as f64) / 1024.0 / 1024.0,
        version: String::new(),
        error: String::new(),
    }
}

/// 在指定目录（不递归）下找第一个权重文件（.pt/.pth/.bin/.safetensors�?
fn find_weights_in_dir(dir: &std::path::Path) -> Option<PathBuf> {
    if !dir.is_dir() {
        return None;
    }
    for entry in std::fs::read_dir(dir).into_iter().flatten().flatten() {
        let p = entry.path();
        if p.is_file() && is_weights_file(&p) {
            return Some(p);
        }
    }
    None
}

/// 递归扫描 base 目录（限定深度）下第一个权重文�?
fn find_weights_recursive(base: &std::path::Path, max_depth: usize) -> Option<PathBuf> {
    if !base.is_dir() {
        return None;
    }
    walkdir::WalkDir::new(base)
        .max_depth(max_depth)
        .follow_links(false)
        .into_iter()
        .filter_map(|e| e.ok())
        .find(|e| e.file_type().is_file() && is_weights_file(e.path()))
        .map(|e| e.path().to_path_buf())
}

fn is_weights_file(p: &std::path::Path) -> bool {
    // 跳过 ModelScope / HF 的部分下载占位目录（"." 开头的隐藏 / "._____temp" 之类）
    if p.components().any(|c| {
        c.as_os_str().to_str().is_some_and(|s| {
            s.starts_with("._____")
                || s == ".locks"
                || s == ".no_exist"
                || s == ".cache_huggingface"
        })
    }) {
        return false;
    }
    p.extension()
        .and_then(|e| e.to_str())
        .is_some_and(|e| matches!(e, "pt" | "pth" | "bin" | "safetensors"))
}

/// 文件路径（lower-cased）是否包含任一关键字 — 防止跨模型误归
fn path_matches(p: &std::path::Path, id_key: &str, repo_key: &str) -> bool {
    let s = p.to_string_lossy().to_lowercase();
    s.contains(id_key) || s.contains(repo_key)
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
    if !dir.is_dir() {
        return false;
    }
    walk_dir_for_ext(dir, exts, 3)
}

fn walk_dir_for_ext(dir: &std::path::Path, exts: &[&str], depth: u32) -> bool {
    if depth == 0 {
        return false;
    }
    walkdir::WalkDir::new(dir)
        .max_depth(depth as usize)
        .follow_links(false)
        .into_iter()
        .filter_map(|e| e.ok())
        .any(|e| {
            e.file_type().is_file()
                && e.path()
                    .extension()
                    .and_then(|x| x.to_str())
                    .is_some_and(|x| exts.contains(&x))
        })
}

pub fn dir_size(dir: &std::path::Path) -> u64 {
    let mut total = 0u64;
    for entry in walkdir::WalkDir::new(dir)
        .follow_links(false)
        .into_iter()
        .flatten()
    {
        if entry.file_type().is_file() {
            total += entry.metadata().map(|m| m.len()).unwrap_or(0);
        }
    }
    total
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::core::config::constants::model_cache_dir;

    #[test]
    fn finds_moldet_in_subdir() {
        // 模拟用户实际布局：~/.cache/mbforge/models/moldetv2-doc/<file>.pt
        let info = RESOURCE_CATALOG.iter().find(|r| r.id == "moldet").unwrap();
        let status = check_model_file(info);
        if model_cache_dir().join("moldetv2-doc").exists() {
            assert_eq!(
                status.status,
                ResourceStatus::Ready,
                "moldet should be Ready"
            );
            assert!(!status.local_path.is_empty());
            eprintln!("moldet local_path = {}", status.local_path);
        }
    }

    #[test]
    fn finds_qwen_embedding_in_modelscope_hub() {
        // 用户实际布局：~/.cache/modelscope/hub/Qwen/Qwen3-Embedding-0___6B/
        let info = RESOURCE_CATALOG
            .iter()
            .find(|r| r.id == "embedding")
            .unwrap();
        let status = check_model_snapshot(info);
        let home = directories::UserDirs::new()
            .unwrap()
            .home_dir()
            .to_path_buf();
        let ms_hub = home
            .join(".cache")
            .join("modelscope")
            .join("hub")
            .join("Qwen")
            .join("Qwen3-Embedding-0___6B");
        if ms_hub.exists() {
            assert_eq!(
                status.status,
                ResourceStatus::Ready,
                "embedding should be Ready"
            );
            eprintln!("embedding local_path = {}", status.local_path);
        }
    }

    #[test]
    fn finds_qwen_reranker_in_modelscope_hub() {
        let info = RESOURCE_CATALOG
            .iter()
            .find(|r| r.id == "reranker")
            .unwrap();
        let status = check_model_snapshot(info);
        let home = directories::UserDirs::new()
            .unwrap()
            .home_dir()
            .to_path_buf();
        let ms_hub = home
            .join(".cache")
            .join("modelscope")
            .join("hub")
            .join("Qwen")
            .join("Qwen3-Reranker-0___6B");
        if ms_hub.exists() {
            assert_eq!(
                status.status,
                ResourceStatus::Ready,
                "reranker should be Ready"
            );
            eprintln!("reranker local_path = {}", status.local_path);
        }
    }
}
