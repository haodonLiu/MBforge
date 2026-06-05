use serde::{Deserialize, Serialize};
/// 统一资源管理器 — Rust 侧
///
/// 管理所有外部资源（模型、Python 包、二进制工具）的注册、检查、路径解析。
/// 下载执行通过 HTTP 委托给 Python sidecar。
///
/// - 模型默认从 ModelScope 下载（只下载权重 + 必要配置）
/// - Python 包通过 pip + 清华源安装
use std::path::PathBuf;

// ---------------------------------------------------------------------------
// 数据类型
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum ResourceType {
    Model,
    PythonPackage,
    Binary,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum ResourceStatus {
    Ready,
    NotFound,
    Partial,
    Error,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ResourceInfo {
    pub id: &'static str,
    pub name: &'static str,
    #[serde(rename = "type")]
    pub resource_type: ResourceType,
    pub description: &'static str,
    pub size_mb: u64,
    pub license: &'static str,
    pub ms_repo: &'static str,
    pub download_type: &'static str, // "snapshot" | "file"
    pub ms_file: &'static str,       // 单文件下载时的远程文件名
    pub local_name: &'static str,    // 本地文件名/目录名
    pub pip_name: &'static str,      // Python 包名（非空表示需要 pip 安装）
    pub import_name: &'static str,   // Python import 名
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ResourceStatusResult {
    pub id: String,
    pub name: String,
    #[serde(rename = "type")]
    pub resource_type: ResourceType,
    pub status: ResourceStatus,
    pub local_path: String,
    pub size_mb: f64,
    pub version: String,
    pub error: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EnvironmentReport {
    pub python_version: String,
    pub gpu_available: bool,
    pub gpu_name: String,
    pub cuda_version: String,
    pub summary: String,
    pub resources: Vec<ResourceStatusResult>,
}

// ---------------------------------------------------------------------------
// 资源目录（编译期常量）
// ---------------------------------------------------------------------------

const RESOURCE_CATALOG: &[ResourceInfo] = &[
    // ──── 模型 ────
    ResourceInfo {
        id: "embedding",
        name: "Qwen3-Embedding-0.6B",
        resource_type: ResourceType::Model,
        description: "通义千问3 嵌入模型 (0.6B) — 语义检索",
        size_mb: 1152,
        license: "Apache-2.0",
        ms_repo: "Qwen/Qwen3-Embedding-0.6B",
        download_type: "snapshot",
        ms_file: "",
        local_name: "Qwen3-Embedding-0.6B",
        pip_name: "",
        import_name: "",
    },
    ResourceInfo {
        id: "reranker",
        name: "Qwen3-Reranker-0.6B",
        resource_type: ResourceType::Model,
        description: "通义千问3 重排序模型 (0.6B) — 结果精排",
        size_mb: 1152,
        license: "Apache-2.0",
        ms_repo: "Qwen/Qwen3-Reranker-0.6B",
        download_type: "snapshot",
        ms_file: "",
        local_name: "Qwen3-Reranker-0.6B",
        pip_name: "",
        import_name: "",
    },
    ResourceInfo {
        id: "moldet",
        name: "MolDetv2",
        resource_type: ResourceType::Model,
        description: "MolDetv2 分子结构检测 (YOLO)",
        size_mb: 25,
        license: "Apache-2.0",
        ms_repo: "yujieq/MolDetect",
        download_type: "file",
        ms_file: "best.pt",
        local_name: "moldetv2-doc.pt",
        pip_name: "",
        import_name: "",
    },
    ResourceInfo {
        id: "molscribe",
        name: "MolScribe",
        resource_type: ResourceType::Model,
        description: "MolScribe 分子图像 → SMILES",
        size_mb: 6186,
        license: "MIT",
        ms_repo: "yujieq/MolScribe",
        download_type: "snapshot",
        ms_file: "",
        local_name: "MolScribe",
        pip_name: "",
        import_name: "",
    },
    // ──── Python 包 ────
    ResourceInfo {
        id: "rdkit",
        name: "RDKit",
        resource_type: ResourceType::PythonPackage,
        description: "分子信息学: SMILES 解析、分子属性计算",
        size_mb: 0,
        license: "BSD-3",
        ms_repo: "",
        download_type: "",
        ms_file: "",
        local_name: "",
        pip_name: "rdkit",
        import_name: "rdkit",
    },
    ResourceInfo {
        id: "torch",
        name: "PyTorch",
        resource_type: ResourceType::PythonPackage,
        description: "深度学习框架 (CUDA 12.8)",
        size_mb: 0,
        license: "BSD-3",
        ms_repo: "",
        download_type: "",
        ms_file: "",
        local_name: "",
        pip_name: "torch",
        import_name: "torch",
    },
    ResourceInfo {
        id: "sentence_transformers",
        name: "Sentence Transformers",
        resource_type: ResourceType::PythonPackage,
        description: "文本嵌入 + CrossEncoder 框架",
        size_mb: 0,
        license: "Apache-2.0",
        ms_repo: "",
        download_type: "",
        ms_file: "",
        local_name: "",
        pip_name: "sentence-transformers",
        import_name: "sentence_transformers",
    },
    ResourceInfo {
        id: "transformers",
        name: "Transformers",
        resource_type: ResourceType::PythonPackage,
        description: "Hugging Face 模型加载框架",
        size_mb: 0,
        license: "Apache-2.0",
        ms_repo: "",
        download_type: "",
        ms_file: "",
        local_name: "",
        pip_name: "transformers",
        import_name: "transformers",
    },
    ResourceInfo {
        id: "ultralytics",
        name: "Ultralytics",
        resource_type: ResourceType::PythonPackage,
        description: "YOLO 目标检测框架 (MolDet 依赖)",
        size_mb: 0,
        license: "AGPL-3.0",
        ms_repo: "",
        download_type: "",
        ms_file: "",
        local_name: "",
        pip_name: "ultralytics",
        import_name: "ultralytics",
    },
    // ──── 二进制 ────
    ResourceInfo {
        id: "pdfium",
        name: "PDFium",
        resource_type: ResourceType::Binary,
        description: "PDF 渲染引擎 (Rust 侧编译依赖)",
        size_mb: 0,
        license: "Apache-2.0",
        ms_repo: "",
        download_type: "",
        ms_file: "",
        local_name: "",
        pip_name: "",
        import_name: "",
    },
];

// ---------------------------------------------------------------------------
// 路径解析
// ---------------------------------------------------------------------------

/// 获取模型缓存目录（优先环境变量 MBFORGE_MODEL_CACHE_DIR，默认 ~/.cache/mbforge/models）
pub fn model_cache_dir() -> PathBuf {
    if let Ok(dir) = std::env::var("MBFORGE_MODEL_CACHE_DIR") {
        return PathBuf::from(dir);
    }
    if let Some(home) = directories::UserDirs::new().map(|u| u.home_dir().to_path_buf()) {
        return home.join(".cache").join("mbforge").join("models");
    }
    PathBuf::from(".cache/mbforge/models")
}

/// 检查 snapshot 类型模型是否已下载
fn check_model_snapshot(info: &ResourceInfo) -> ResourceStatusResult {
    let cache = model_cache_dir();
    let repo_name = info.ms_repo.split('/').last().unwrap_or(info.ms_repo);

    // 1. MBForge 缓存（直接名称 + 编码名称）
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
                let dir = home
                    .join(".cache")
                    .join("modelscope")
                    .join(subdir)
                    .join(ms_org)
                    .join(name);
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

    // 4. HF_HOME（HuggingFace 缓存布局: hub/models--<org>--<repo>/snapshots/<commit>/）
    if let Ok(hf_home) = std::env::var("HF_HOME") {
        let hf_hub = PathBuf::from(&hf_home).join("hub");
        let encoded_name = format!("models--{}", info.ms_repo.replace('/', "--"));
        let snapshots = hf_hub.join(&encoded_name).join("snapshots");
        if snapshots.exists() {
            // 遍历 snapshots 下的 commit 目录
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
        // 兼容直接路径（用户手动放置）
        let direct = PathBuf::from(&hf_home).join(repo_name);
        if let Some(result) = check_dir_for_weights(info, &direct) {
            return result;
        }
    }

    not_found(info)
}

/// 检查目录中是否有模型权重文件
fn check_dir_for_weights(
    info: &ResourceInfo,
    dir: &std::path::Path,
) -> Option<ResourceStatusResult> {
    if !dir.exists() {
        return None;
    }
    // 检查常见权重格式
    let has_weights = has_file_with_ext(dir, &["bin", "safetensors", "pt", "pth", "onnx"]);
    if !has_weights {
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

/// 检查单文件类型模型
fn check_model_file(info: &ResourceInfo) -> ResourceStatusResult {
    let cache = model_cache_dir();
    let local_name = if info.local_name.is_empty() {
        format!("{}.pt", info.id)
    } else {
        info.local_name.to_string()
    };

    // 直接路径
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

    // 子目录
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

/// 检查 Python 包是否安装（通过子进程，带超时）
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
    // 尝试 python，再尝试 python3
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

/// 检查 PDFium
fn check_pdfium() -> ResourceStatusResult {
    let info = RESOURCE_CATALOG
        .iter()
        .find(|r| r.id == "pdfium")
        .expect("pdfium must be in RESOURCE_CATALOG");

    // Rust vendor 目录
    if let Ok(manifest) = std::env::var("CARGO_MANIFEST_DIR") {
        let pdfium_lib = PathBuf::from(manifest).join("vendor/pdfium/release/lib");
        if pdfium_lib.exists()
            && std::fs::read_dir(&pdfium_lib)
                .map(|mut d| d.next().is_some())
                .unwrap_or(false)
        {
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

    // 环境变量
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

// ---------------------------------------------------------------------------
// 工具函数
// ---------------------------------------------------------------------------

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
    walk_dir_for_ext(dir, exts, 3) // 最多递归 3 层
}

fn walk_dir_for_ext(dir: &std::path::Path, exts: &[&str], depth: u32) -> bool {
    if depth == 0 {
        return false;
    }
    let entries = match std::fs::read_dir(dir) {
        Ok(e) => e,
        Err(_) => return false,
    };
    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_file() {
            if let Some(ext) = path.extension().and_then(|e| e.to_str()) {
                if exts.contains(&ext) {
                    return true;
                }
            }
        } else if path.is_dir() && walk_dir_for_ext(&path, exts, depth - 1) {
            return true;
        }
    }
    false
}

fn dir_size(dir: &std::path::Path) -> u64 {
    // 使用 walkdir 处理符号链接循环（不跟随 symlink 目录）
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

/// 获取 Python 版本
fn get_python_version() -> String {
    let cmd = "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')";
    ["python", "python3"]
        .iter()
        .find_map(|py| {
            std::process::Command::new(py)
                .args(["-c", cmd])
                .stdout(std::process::Stdio::piped())
                .stderr(std::process::Stdio::null())
                .output()
                .ok()
                .filter(|o| o.status.success())
                .and_then(|o| String::from_utf8(o.stdout).ok())
                .map(|s| s.trim().to_string())
        })
        .unwrap_or_else(|| "unknown".to_string())
}

/// 检测 GPU（通过 nvidia-smi）
fn detect_gpu() -> (bool, String, String) {
    let output = std::process::Command::new("nvidia-smi")
        .args(["--query-gpu=name,driver_version", "--format=csv,noheader"])
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::null())
        .output();

    match output {
        Ok(out) if out.status.success() => {
            let text = String::from_utf8_lossy(&out.stdout);
            let parts: Vec<&str> = text.trim().split(',').collect();
            let name = parts.first().unwrap_or(&"").trim().to_string();
            let cuda = parts.get(1).unwrap_or(&"").trim().to_string();
            (true, name, cuda)
        }
        _ => (false, String::new(), String::new()),
    }
}

// ---------------------------------------------------------------------------
// 公开 API
// ---------------------------------------------------------------------------

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
                check_pdfium()
            } else {
                not_found(info)
            }
        }
    }
}

/// 全量环境检查
pub fn check_all_resources() -> EnvironmentReport {
    let python_version = get_python_version();
    let (gpu_available, gpu_name, cuda_version) = detect_gpu();

    let mut resources = Vec::new();
    for info in RESOURCE_CATALOG {
        resources.push(check_resource(info.id));
    }

    let ready = resources
        .iter()
        .filter(|r| r.status == ResourceStatus::Ready)
        .count();
    let total = resources.len();

    EnvironmentReport {
        python_version,
        gpu_available,
        gpu_name,
        cuda_version,
        summary: format!("{}/{} resources ready", ready, total),
        resources,
    }
}

/// 获取已下载模型的本地路径（供模型加载使用）
pub fn get_model_path(resource_id: &str) -> Option<PathBuf> {
    let status = check_resource(resource_id);
    if status.status == ResourceStatus::Ready && !status.local_path.is_empty() {
        Some(PathBuf::from(&status.local_path))
    } else {
        None
    }
}

/// 将所有模型路径写入共享 JSON 文件，供 Python sidecar 读取。
/// 在 main.rs setup 中、spawn Python 之前调用。
pub fn write_resolved_paths() {
    use std::io::Write;

    let config_dir = directories::ProjectDirs::from("", "", "MBForge")
        .map(|d| d.config_dir().to_path_buf())
        .unwrap_or_else(|| PathBuf::from(".").join(".config").join("MBForge"));
    let _ = std::fs::create_dir_all(&config_dir);
    let path = config_dir.join("resolved_paths.json");

    let mut map = serde_json::Map::new();
    for info in RESOURCE_CATALOG {
        if info.resource_type == ResourceType::Model {
            if let Some(p) = get_model_path(info.id) {
                map.insert(
                    info.id.to_string(),
                    serde_json::Value::String(p.to_string_lossy().to_string()),
                );
            }
        }
    }

    let json = serde_json::Value::Object(map);
    if let Ok(mut f) = std::fs::File::create(&path) {
        let _ = f.write_all(
            serde_json::to_string_pretty(&json)
                .unwrap_or_default()
                .as_bytes(),
        );
        log::info!("Wrote resolved model paths to {}", path.display());
    }
}

// ---------------------------------------------------------------------------
// Tauri Commands
// ---------------------------------------------------------------------------

#[tauri::command]
pub fn resources_check() -> EnvironmentReport {
    check_all_resources()
}

#[tauri::command]
pub fn resources_status(resource_id: String) -> ResourceStatusResult {
    check_resource(&resource_id)
}

#[tauri::command]
pub fn resources_get_model_path(resource_id: String) -> Option<String> {
    get_model_path(&resource_id).map(|p| p.to_string_lossy().to_string())
}

/// 获取资源目录（纯元数据，不含状态）
#[tauri::command]
pub fn resources_catalog() -> Vec<serde_json::Value> {
    RESOURCE_CATALOG
        .iter()
        .map(|info| {
            serde_json::json!({
                "id": info.id,
                "name": info.name,
                "type": info.resource_type,
                "description": info.description,
                "size_mb": info.size_mb,
                "license": info.license,
                "ms_repo": info.ms_repo,
                "pip_name": info.pip_name,
            })
        })
        .collect()
}

// ---------------------------------------------------------------------------
// Default 实现（用于错误情况）
// ---------------------------------------------------------------------------

impl Default for ResourceStatusResult {
    fn default() -> Self {
        Self {
            id: String::new(),
            name: String::new(),
            resource_type: ResourceType::Model,
            status: ResourceStatus::NotFound,
            local_path: String::new(),
            size_mb: 0.0,
            version: String::new(),
            error: String::new(),
        }
    }
}
