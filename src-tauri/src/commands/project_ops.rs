//! 项目操作命令 — 创建、打开、扫描项目

use std::path::PathBuf;

/// 创建或打开项目（Tauri 命令）
///
/// 如果目录不存在则创建，如果目录存在但不是项目则初始化。
/// 返回项目信息。
#[tauri::command]
pub fn open_project(root: String, name: Option<String>) -> Result<serde_json::Value, String> {
    let path = PathBuf::from(&root);

    // 尝试打开已有项目
    if let Some(project) = crate::core::project::Project::open(&path) {
        return Ok(project_json(&project));
    }

    // 目录不存在或不是项目 → 创建
    let project = crate::core::project::Project::create(&path)
        .ok_or_else(|| format!("无法创建项目: {}", root))?;

    Ok(project_json(&project))
}

/// 扫描项目文件
#[tauri::command]
pub fn scan_project_files(root: String) -> Result<serde_json::Value, String> {
    let path = PathBuf::from(&root);
    let mut project = crate::core::project::Project::open(&path)
        .ok_or_else(|| format!("项目不存在: {}", root))?;

    let docs = project.scan_files();
    Ok(serde_json::json!({
        "success": true,
        "documents": docs_json(&docs),
    }))
}

/// 列出项目文档
#[tauri::command]
pub fn list_project_documents(root: String, doc_type: Option<String>) -> Result<serde_json::Value, String> {
    let path = PathBuf::from(&root);
    let project = crate::core::project::Project::open(&path)
        .ok_or_else(|| format!("项目不存在: {}", root))?;

    let docs = project.list_documents().to_vec();
    let filtered: Vec<_> = match doc_type.as_deref() {
        Some(dt) if !dt.is_empty() => docs.into_iter().filter(|d| d.doc_type == dt).collect(),
        _ => docs,
    };

    Ok(serde_json::json!({
        "success": true,
        "documents": docs_json(&filtered),
    }))
}

fn project_json(project: &crate::core::project::Project) -> serde_json::Value {
    // Don't call list_documents() here - it loads the full index
    // which may trigger slow file system operations
    serde_json::json!({
        "success": true,
        "project": {
            "name": project.root.file_name().and_then(|n| n.to_str()).unwrap_or("Untitled"),
            "root": project.root,
            "document_count": 0, // Will be fetched separately if needed
        },
    })
}

fn docs_json(docs: &[crate::core::project::DocumentEntry]) -> Vec<serde_json::Value> {
    docs.iter().map(|d| {
        serde_json::json!({
            "doc_id": d.doc_id,
            "path": d.path,
            "doc_type": d.doc_type,
            "title": d.title,
            "indexed": d.indexed,
        })
    }).collect()
}
