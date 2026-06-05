//! File system tools — grep, list, read, glob, project info.
//!
//! All tools delegate to a `&str` project root captured at registration time.

use std::collections::HashMap;

use grep_regex::RegexMatcherBuilder;
use grep_searcher::sinks::UTF8;
use grep_searcher::SearcherBuilder;
use ignore::WalkBuilder;

use crate::core::helpers;
use crate::core::agent::tools::{ToolInfo, ToolRegistry};

/// Register all file-system native tools.
pub fn register(registry: &mut ToolRegistry, project_root: &str) {
    let root = project_root.to_string();

    // grep_search — ripgrep
    let r = root.clone();
    registry.register_with_fn(
        ToolInfo::new(
            "grep_search",
            "在项目文件中正则搜索内容（ripgrep 级性能）",
            {
                let mut p = HashMap::new();
                p.insert("pattern".into(), serde_json::json!({"type": "string"}));
                p.insert("path".into(), serde_json::json!({"type": "string"}));
                p.insert("max_results".into(), serde_json::json!({"type": "integer"}));
                p
            },
        ),
        Box::new(move |args| {
            let pattern = args["pattern"].as_str().unwrap_or("");
            let search_path = args["path"].as_str().unwrap_or("");
            let max_results = args["max_results"].as_u64().unwrap_or(20) as usize;
            native_grep_search(&r, pattern, search_path, max_results)
        }),
    );

    // list_files — ignore crate (.gitignore aware)
    let r = root.clone();
    registry.register_with_fn(
        ToolInfo::new(
            "list_files",
            "列出项目中的文件（遵循 .gitignore）",
            {
                let mut p = HashMap::new();
                p.insert("pattern".into(), serde_json::json!({"type": "string"}));
                p.insert("max_results".into(), serde_json::json!({"type": "integer"}));
                p
            },
        ),
        Box::new(move |args| {
            let pattern = args["pattern"].as_str().unwrap_or("");
            let max_results = args["max_results"].as_u64().unwrap_or(50) as usize;
            native_list_files(&r, pattern, max_results)
        }),
    );

    // read_file
    let r = root.clone();
    registry.register_with_fn(
        ToolInfo::new("read_file", "读取项目中指定文件的内容", {
            let mut p = HashMap::new();
            p.insert("path".into(), serde_json::json!({"type": "string"}));
            p.insert("max_lines".into(), serde_json::json!({"type": "integer"}));
            p
        }),
        Box::new(move |args| {
            let file_path = args["path"].as_str().unwrap_or("");
            let max_lines = args["max_lines"].as_u64().unwrap_or(200) as usize;
            native_read_file(&r, file_path, max_lines)
        }),
    );

    // get_project_info
    let r = root.clone();
    registry.register_with_fn(
        ToolInfo::new(
            "get_project_info",
            "获取项目基本信息（文件数、目录结构等）",
            HashMap::new(),
        ),
        Box::new(move |_args| native_get_project_info(&r)),
    );

    // glob_search — globset crate
    let r = root.clone();
    registry.register_with_fn(
        ToolInfo::new("glob_search", "按 glob 模式搜索文件名", {
            let mut p = HashMap::new();
            p.insert("pattern".into(), serde_json::json!({"type": "string"}));
            p.insert("max_results".into(), serde_json::json!({"type": "integer"}));
            p
        }),
        Box::new(move |args| {
            let pattern = args["pattern"].as_str().unwrap_or("");
            let max_results = args["max_results"].as_u64().unwrap_or(50) as usize;
            native_glob_search(&r, pattern, max_results)
        }),
    );
}

fn native_grep_search(root: &str, pattern: &str, search_path: &str, max_results: usize) -> String {
    let matcher = match RegexMatcherBuilder::new().build(pattern) {
        Ok(m) => m,
        Err(e) => return format!("Invalid regex: {}", e),
    };

    let target = if search_path.is_empty() {
        std::path::PathBuf::from(root)
    } else {
        let p = std::path::PathBuf::from(root).join(search_path);
        // 使用 helpers 中的统一路径安全检查
        if helpers::assert_within_root(root, &p).is_err() {
            return "Access denied: path escapes project root".to_string();
        }
        p
    };

    let mut results = Vec::new();
    let mut searcher = SearcherBuilder::new().line_number(true).build();

    let _ = searcher.search_path(
        &matcher,
        &target,
        UTF8(|line_number, line| {
            if results.len() >= max_results {
                return Ok(false);
            }
            results.push(format!(
                "{}:{}:{}",
                target.display(),
                line_number,
                line.trim()
            ));
            Ok(true)
        }),
    );

    if results.is_empty() {
        "No matches found".to_string()
    } else {
        results.join("\n")
    }
}

fn native_list_files(root: &str, pattern: &str, max_results: usize) -> String {
    let walker = WalkBuilder::new(root).build();
    let glob = if pattern.is_empty() {
        None
    } else {
        match globset::Glob::new(pattern) {
            Ok(g) => Some(g.compile_matcher()),
            Err(e) => return format!("Invalid glob: {}", e),
        }
    };

    let mut results = Vec::new();
    for entry in walker.filter_map(|e| e.ok()) {
        if results.len() >= max_results {
            break;
        }
        let path = entry.path();
        if path.is_dir() {
            continue;
        }
        if let Some(ref g) = glob {
            if !g.is_match(path) {
                continue;
            }
        }
        if let Ok(rel) = path.strip_prefix(root) {
            results.push(rel.to_string_lossy().to_string());
        }
    }

    if results.is_empty() {
        "No files found".to_string()
    } else {
        format!("Found {} files:\n{}", results.len(), results.join("\n"))
    }
}

fn native_read_file(root: &str, file_path: &str, max_lines: usize) -> String {
    let path = std::path::PathBuf::from(root).join(file_path);
    // 使用 helpers 中的统一路径安全检查
    if helpers::assert_within_root(root, &path).is_err() {
        return "Access denied: path escapes project root".to_string();
    }
    if !path.exists() {
        return format!("File not found: {}", file_path);
    }
    let content = match std::fs::read_to_string(&path) {
        Ok(c) => c,
        Err(e) => return format!("Read error: {}", e),
    };
    let lines: Vec<&str> = content.lines().take(max_lines).collect();
    let total = content.lines().count();
    let truncated = if total > max_lines {
        format!("\n... ({} more lines)", total - max_lines)
    } else {
        String::new()
    };
    format!("{}{}", lines.join("\n"), truncated)
}

fn native_get_project_info(root: &str) -> String {
    let root_path = std::path::PathBuf::from(root);
    let mut file_count = 0u64;
    let mut dir_count = 0u64;
    let mut total_size = 0u64;
    let mut ext_counts: HashMap<String, u64> = HashMap::new();

    let walker = WalkBuilder::new(root).build();
    for entry in walker.filter_map(|e| e.ok()) {
        if entry.path().is_dir() {
            dir_count += 1;
        } else {
            file_count += 1;
            if let Ok(meta) = entry.metadata() {
                total_size += meta.len();
            }
            if let Some(ext) = entry.path().extension().and_then(|e| e.to_str()) {
                *ext_counts.entry(ext.to_string()).or_default() += 1;
            }
        }
    }

    let mut lines = vec![
        format!(
            "Project: {}",
            root_path.file_name().unwrap_or_default().to_string_lossy()
        ),
        format!("Path: {}", root),
        format!("Files: {}", file_count),
        format!("Directories: {}", dir_count),
        format!("Total size: {:.2} MB", total_size as f64 / 1_048_576.0),
    ];

    if !ext_counts.is_empty() {
        let mut sorted: Vec<_> = ext_counts.into_iter().collect();
        sorted.sort_by(|a, b| b.1.cmp(&a.1));
        lines.push("File types:".to_string());
        for (ext, count) in sorted.iter().take(10) {
            lines.push(format!("  .{}: {}", ext, count));
        }
    }

    lines.join("\n")
}

fn native_glob_search(root: &str, pattern: &str, max_results: usize) -> String {
    let glob = match globset::Glob::new(pattern) {
        Ok(g) => g.compile_matcher(),
        Err(e) => return format!("Invalid glob: {}", e),
    };

    let walker = WalkBuilder::new(root).build();
    let mut results = Vec::new();
    for entry in walker.filter_map(|e| e.ok()) {
        if results.len() >= max_results {
            break;
        }
        if entry.path().is_file() && glob.is_match(entry.path()) {
            if let Ok(rel) = entry.path().strip_prefix(root) {
                results.push(rel.to_string_lossy().to_string());
            }
        }
    }

    if results.is_empty() {
        "No files matched".to_string()
    } else {
        format!("Found {} files:\n{}", results.len(), results.join("\n"))
    }
}
