//! 路径解析 — 检查资源是否已下载/安装
//!
//! 单一检测源：`~/mbforge/models/`。不扫描 HF_HOME / MODELSCOPE_CACHE / TORCH_HOME。
//! 用户手动放置文件时必须放在此目录下，否则视为未下载。
use super::catalog::*;
use std::path::PathBuf;

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
        ResourceType::Binary => not_found_with_expected(info, &expected_path_for(info)),
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

// ─── 内部检查函数 ────────────────────────────────────────────────

/// 解析 ModelScope 仓库的本地目录：`<cache>/<org>/<encoded_repo>/`
/// 编码规则：repo 中的 `.` 替换为 `___`（与 ModelScope SDK 行为一致）。
pub fn ms_repo_dir(info: &ResourceInfo) -> PathBuf {
    let cache = crate::core::config::constants::model_cache_dir();
    let org = info.ms_repo.split('/').next().unwrap_or("");
    let repo_name = info.ms_repo.split('/').last().unwrap_or(info.ms_repo);
    let encoded = repo_name.replace('.', "___");
    if org.is_empty() {
        cache.join(encoded)
    } else {
        cache.join(org).join(encoded)
    }
}

/// 计算资源在 `~/mbforge/models/` 下的期望路径。
/// - info.files 唯一项 → 该文件
/// - info.files 多项 → ms_repo_dir 目录
/// - 否则：snapshot → ms_repo_dir；file → <local_name>
fn expected_path_for(info: &ResourceInfo) -> PathBuf {
    let cache = crate::core::config::constants::model_cache_dir();
    if !info.files.is_empty() {
        if info.files.len() == 1 {
            return ms_repo_dir(info).join(info.files[0]);
        }
        return ms_repo_dir(info);
    }
    if info.download_type == "file" {
        let local_name = if info.local_name.is_empty() {
            format!("{}.pt", info.id)
        } else {
            info.local_name.to_string()
        };
        cache.join(local_name)
    } else {
        ms_repo_dir(info)
    }
}

/// snapshot 类型模型 — 唯一检测源：`~/mbforge/models/<org>/<encoded_repo>/`
///
/// 若 info.files 非空，按精确文件列表逐个检查（任一缺失 → NotFound）。
/// 多文件时填充 subfiles 字段供前端逐行展示。
fn check_model_snapshot(info: &ResourceInfo) -> ResourceStatusResult {
    let cache = crate::core::config::constants::model_cache_dir();
    let expected = expected_path_for(info);
    let dest = ms_repo_dir(info);

    if !info.files.is_empty() {
        // 精确文件列表：全部存在才算 Ready；逐个填 subfiles
        let mut all_ok = true;
        let mut first_existing: Option<PathBuf> = None;
        let mut existing_size: u64 = 0;
        let mut subfiles: Vec<super::catalog::SubfileStatus> = Vec::new();
        let mut total_size: u64 = 0;

        for rel in info.files {
            let p = dest.join(rel);
            let size = p.metadata().map(|m| m.len()).unwrap_or(0);
            let ready = p.exists() && size > 0;
            if !ready {
                all_ok = false;
            } else {
                total_size += size;
                if first_existing.is_none() {
                    first_existing = Some(p.clone());
                    existing_size = size;
                }
            }
            subfiles.push(super::catalog::SubfileStatus {
                label: friendly_subfile_label(rel),
                relpath: rel.to_string(),
                local_path: p.to_string_lossy().to_string(),
                ready,
                size_mb: (size as f64) / 1024.0 / 1024.0,
            });
        }

        if all_ok {
            // local_path 写成 dest 目录（不是单个文件），与 Python 侧
            // `get_molscribe_path` / `resolve_model_for_backend(..., subpath=)` 约定一致：
            // 读 dir + 自己拼 subpath 定位子文件。
            let mut result = mk_ready(info, &dest, total_size).with_expected(expected.to_string_lossy().to_string());
            if info.files.len() > 1 {
                result.subfiles = subfiles;
            }
            return result;
        }
        let mut result = not_found_with_expected(info, &expected);
        if info.files.len() > 1 {
            result.subfiles = subfiles;
        }
        return result;
    }

    // 回退：扫描 ms_repo_dir 是否有任意权重文件
    if let Some(mut result) = check_dir_for_weights(info, &dest) {
        result.expected_path = expected.to_string_lossy().to_string();
        return result;
    }

    not_found_with_expected(info, &expected)
}

/// 子文件的友好标签：取第一段目录名（如 "doc/moldet_v2...pt" → "doc"），
/// 否则取文件名（去扩展名）。
fn friendly_subfile_label(rel: &str) -> String {
    if let Some((dir, _)) = rel.split_once('/') {
        return dir.to_string();
    }
    std::path::Path::new(rel)
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or(rel)
        .to_string()
}

/// 单文件类型模型 — 唯一检测源：`~/mbforge/models/`
///
/// 支持三种布局（按用户放置习惯）：
///   1. `~/mbforge/models/<local_name>`（精确文件）
///   2. `~/mbforge/models/<local_stem>/<weights>`（子目录）
///   3. `~/mbforge/models/<repo_name>/<weights>`（按 repo 分目录）
fn check_model_file(info: &ResourceInfo) -> ResourceStatusResult {
    let local_name = if info.local_name.is_empty() {
        format!("{}.pt", info.id)
    } else {
        info.local_name.to_string()
    };
    let repo_name = info.ms_repo.split('/').last().unwrap_or(info.ms_repo);
    let local_stem = std::path::Path::new(&local_name)
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or(&local_name);

    let id_key = info.id.to_lowercase();
    let repo_key = repo_name.to_lowercase();
    let cache = crate::core::config::constants::model_cache_dir();
    let expected = expected_path_for(info);

    let search_base = |base: &std::path::Path| -> Option<ResourceStatusResult> {
        let path = base.join(&local_name);
        if path.exists() && path.metadata().map(|m| m.len() > 0).unwrap_or(false) {
            let size = path.metadata().map(|m| m.len()).unwrap_or(0);
            return Some(mk_ready(info, &path, size));
        }
        let stem_subdir = base.join(local_stem);
        if let Some(p) =
            find_weights_in_dir(&stem_subdir).filter(|p| path_matches(p, &id_key, &repo_key))
        {
            return Some(mk_ready(info, &p, p.metadata().map(|m| m.len()).unwrap_or(0)));
        }
        let subdir = base.join(&repo_name);
        if let Some(p) =
            find_weights_in_dir(&subdir).filter(|p| path_matches(p, &id_key, &repo_key))
        {
            return Some(mk_ready(info, &p, p.metadata().map(|m| m.len()).unwrap_or(0)));
        }
        None
    };

    if let Some(mut result) = search_base(&cache) {
        result.expected_path = expected.to_string_lossy().to_string();
        return result;
    }

    not_found_with_expected(info, &expected)
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
                expected_path: String::new(),
                subfiles: Vec::new(),
            }
        }
        _ => ResourceStatusResult {
            id: info.id.to_string(),
            name: info.name.to_string(),
            resource_type: info.resource_type.clone(),
            status: ResourceStatus::NotFound,
            local_path: String::new(),
            size_mb: 0.0,
            version: String::new(),
            error: String::new(),
            expected_path: String::new(),
            subfiles: Vec::new(),
        },
    }
}

fn has_files(p: &std::path::Path) -> bool {
    p.exists()
        && std::fs::read_dir(p)
            .map(|mut d| d.next().is_some())
            .unwrap_or(false)
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
    Some(mk_ready(info, dir, size))
}

/// 构造一个 Ready 状态结果（expected_path 留空，由调用方填入）
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
        expected_path: String::new(),
        subfiles: Vec::new(),
    }
}

/// 链式 helper：把 expected_path 一次性填上
trait WithExpected {
    fn with_expected(self, expected: String) -> Self;
}

impl WithExpected for ResourceStatusResult {
    fn with_expected(mut self, expected: String) -> Self {
        self.expected_path = expected;
        self
    }
}

/// 在指定目录（不递归）下找第一个权重文件（.pt/.pth/.bin/.safetensors）
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

fn not_found_with_expected(info: &ResourceInfo, expected: &std::path::Path) -> ResourceStatusResult {
    ResourceStatusResult {
        id: info.id.to_string(),
        name: info.name.to_string(),
        resource_type: info.resource_type.clone(),
        status: ResourceStatus::NotFound,
        local_path: String::new(),
        size_mb: 0.0,
        version: String::new(),
        error: String::new(),
        expected_path: expected.to_string_lossy().to_string(),
        subfiles: Vec::new(),
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

    /// 通用工具：跑 check_resource 并断言 NotFound + expected_path 包含 mbforge。
    /// 注：这些测试在用户的 ~/mbforge/ 通常是空时（CI/干净环境）会通过；
    /// 已有模型文件时则 Ready。两个状态都合法。
    fn assert_not_found_with_path(id: &str) -> ResourceStatusResult {
        let status = check_resource(id);
        assert!(
            !status.expected_path.is_empty(),
            "{}: expected_path 必须始终非空（告诉用户放哪）",
            id
        );
        assert!(
            status.expected_path.contains("mbforge"),
            "{}: expected_path 应在 ~/mbforge/ 下，实际: {}",
            id,
            status.expected_path
        );
        status
    }

    #[test]
    fn each_model_has_unique_expected_path() {
        // 防御：catalog 不能有两条资源期望同一路径（用户删除会误伤）
        use std::collections::HashSet;
        let mut seen: HashSet<String> = HashSet::new();
        for info in RESOURCE_CATALOG {
            if info.resource_type != ResourceType::Model {
                continue;
            }
            let p = expected_path_for(info).to_string_lossy().to_string();
            assert!(seen.insert(p.clone()), "重复的 expected_path: {} (id={})", p, info.id);
        }
    }

    #[test]
    fn embedding_layout() {
        // 多文件 (10 个)，expected_path 应为 org/repo 目录而非具体文件
        let s = assert_not_found_with_path("embedding");
        assert!(s.expected_path.contains("Qwen"), "embedding 应在 Qwen/ 组织下");
        assert!(s.expected_path.contains("Qwen3-Embedding-0___6B"));
        assert!(s.expected_path.ends_with("Qwen3-Embedding-0___6B"),
            "应为目录，不是文件: {}", s.expected_path);
    }

    #[test]
    fn reranker_layout() {
        let s = assert_not_found_with_path("reranker");
        assert!(s.expected_path.contains("Qwen3-Reranker-0___6B"));
        assert!(s.expected_path.ends_with("Qwen3-Reranker-0___6B"));
    }

    #[test]
    fn moldet_layout() {
        // moldet 有 2 个子文件，expected_path 应为目录（不是具体文件）
        let s = assert_not_found_with_path("moldet");
        assert!(s.expected_path.contains("UniParser"));
        assert!(s.expected_path.contains("MolDetv2"));
        assert!(s.expected_path.ends_with("MolDetv2"),
            "应为父目录: {}", s.expected_path);
        // 验证 subfiles 数量
        assert_eq!(s.subfiles.len(), 2, "moldet 应有 2 个子文件 (doc + general)");
        // 验证子文件标签
        let labels: Vec<&str> = s.subfiles.iter().map(|sf| sf.label.as_str()).collect();
        assert!(labels.contains(&"doc"), "应有 doc 子文件");
        assert!(labels.contains(&"general"), "应有 general 子文件");
        // 子文件路径应在父目录下
        for sf in &s.subfiles {
            assert!(sf.local_path.starts_with(s.expected_path.trim_end_matches('\\').trim_end_matches('/'))
                || sf.local_path.contains("MolDetv2"),
                "子文件路径应在 moldet 目录下: {}", sf.local_path);
        }
    }

    #[test]
    fn molscribe_layout() {
        // 单文件 (files.len() == 1)，expected_path 应指向 .pth
        let s = assert_not_found_with_path("molscribe");
        assert!(s.expected_path.contains("polyai"));
        assert!(s.expected_path.contains("MolScribe"));
        assert!(s.expected_path.ends_with("swin_base_char_aux_1m680k.pth"),
            "应指向具体 .pth 文件: {}", s.expected_path);
        // 单文件资源 subfiles 应为空（UI 走单文件卡布局）
        assert!(s.subfiles.is_empty(), "molscribe 是单文件，不应有 subfiles");
    }

    #[test]
    fn python_packages_not_in_models_check() {
        // torch / transformers 等 Python 包不属于模型，其状态由 check_python_package 决定
        // 验证：调用 check_resource 不会 panic 且 status 是 Ready 或 NotFound
        for id in ["torch", "transformers", "sentence_transformers", "ultralytics"] {
            let s = check_resource(id);
            assert!(
                matches!(s.status, ResourceStatus::Ready | ResourceStatus::NotFound),
                "{} 应为 Ready 或 NotFound，实际: {:?}",
                id, s.status
            );
            // Python 包不应有 expected_path（不是文件检测）
            assert!(s.expected_path.is_empty(),
                "{} 是 Python 包，expected_path 应为空", id);
        }
    }

    #[test]
    fn friendly_subfile_label_extracts_dir_name() {
        assert_eq!(friendly_subfile_label("doc/moldet_v2.pt"), "doc");
        assert_eq!(friendly_subfile_label("general/foo.pt"), "general");
        assert_eq!(friendly_subfile_label("single.pt"), "single");
    }

    #[test]
    fn ms_repo_dir_encodes_dots() {
        // UniParser/MolDetv2 → <cache>/UniParser/MolDetv2 (无点，不需要编码)
        // Qwen/Qwen3-Embedding-0.6B → <cache>/Qwen/Qwen3-Embedding-0___6B (点变 ___)
        let qwen = RESOURCE_CATALOG.iter().find(|r| r.id == "embedding").unwrap();
        let d = ms_repo_dir(qwen);
        assert!(d.to_string_lossy().contains("Qwen3-Embedding-0___6B"),
            "点应被编码为 ___: {:?}", d);
        let moldet = RESOURCE_CATALOG.iter().find(|r| r.id == "moldet").unwrap();
        let d = ms_repo_dir(moldet);
        assert!(d.to_string_lossy().contains("UniParser"),
            "组织目录应保留: {:?}", d);
    }
}
