//! 项目操作命令 — 创建、打开、扫描项目

use log::{debug, error, info, warn};
use std::path::PathBuf;
use tauri::Manager;

use crate::core::error::{AppError, ErrorCode};
use crate::core::helpers::clean_path;

/// 创建或打开项目（Tauri 命令）
///
/// 如果目录不存在则创建，如果目录存在但不是项目则初始化。
/// 返回项目信息。
#[tauri::command]
pub fn open_project(
    app: tauri::AppHandle,
    root: String,
    name: Option<String>,
) -> Result<serde_json::Value, String> {
    let root = clean_path(&root);
    info!("project_ops: open_project START");
    debug!("Root: {}", root);
    debug!("Name: {:?}", name);

    let path = PathBuf::from(&root);
    debug!("Path exists: {}", path.exists());
    debug!("Path is directory: {}", path.is_dir());

    // 确保目录存在（处理最近项目路径可能不存在的情况）
    if !path.exists() {
        debug!("Creating directory...");
        match std::fs::create_dir_all(&path) {
            Ok(_) => debug!("Directory created successfully"),
            Err(e) => {
                error!("Failed to create directory: {}", e);
                return Err(
                    AppError::new(ErrorCode::ProjectCreate, format!("创建目录失败: {e}"))
                        .to_string(),
                );
            }
        }
    } else {
        debug!("Directory already exists");
    }

    // 尝试打开已有项目
    debug!("Attempting to open existing project...");
    if let Some(project) = crate::core::project::Project::open(&path) {
        debug!("Found existing project, returning...");
        debug!("Project name: {:?}", project.root.file_name());
        // NOTE: start the ingest worker here (before returning the response)
        // because the worker uses the project path for its own state. The
        // frontend should call `open_project` BEFORE it sets
        // `AppContext.projectRoot`; this preserves the invariant that
        // the worker is up whenever a project is logically "open".
        start_or_restart_ingest_worker(&app, &path);
        let result = project_json(&project);
        debug!(
            "Result: {}",
            serde_json::to_string_pretty(&result).unwrap_or_default()
        );
        info!("project_ops: open_project END (existing)");
        return Ok(result);
    }

    debug!("No existing project, creating new one...");
    // 目录存在但不是项目 → 创建
    match crate::core::project::Project::create(&path) {
        Some(project) => {
            debug!("Project created successfully");
            debug!("Project name: {:?}", project.root.file_name());
            start_or_restart_ingest_worker(&app, &path);
            let result = project_json(&project);
            debug!(
                "Result: {}",
                serde_json::to_string_pretty(&result).unwrap_or_default()
            );
            info!("project_ops: open_project END (created)");
            Ok(result)
        }
        None => {
            error!("Failed to create project");
            warn!("project_ops: open_project END (ERROR)");
            Err(AppError::new(ErrorCode::ProjectCreate, "无法创建项目").to_string())
        }
    }
}

/// 扫描项目文件
#[tauri::command]
pub fn scan_project_files(root: String) -> Result<serde_json::Value, String> {
    let root = clean_path(&root);
    info!("project_ops: scan_project_files START");
    debug!("Root: {}", root);

    let path = PathBuf::from(&root);
    let mut project = crate::core::project::Project::open(&path).ok_or_else(|| {
        debug!("Project not found");
        AppError::new(ErrorCode::ProjectOpen, format!("项目不存在: {root}")).to_string()
    })?;

    debug!("Project found, scanning files...");
    let (new_docs, warnings) = project.scan_files();
    debug!(
        "Scan complete: {} new docs, {} warnings",
        new_docs.len(),
        warnings.len()
    );

    // All known documents (existing + newly scanned) so the UI sees the
    // full picture, not just deltas.
    let all_docs: Vec<_> = project.list_documents().to_vec();
    let result = serde_json::json!({
        "success": true,
        "documents": docs_json(&all_docs),
        "new_documents": docs_json(&new_docs),
        "warnings": warnings_json(&warnings),
    });
    info!("project_ops: scan_project_files END");
    Ok(result)
}

fn warnings_json(warnings: &[crate::core::project::ScanWarning]) -> Vec<serde_json::Value> {
    warnings
        .iter()
        .map(|w| {
            serde_json::json!({
                "path": w.path,
                "message": w.reason,
            })
        })
        .collect()
}

fn docs_json(docs: &[crate::core::project::project::DocumentEntry]) -> Vec<serde_json::Value> {
    docs.iter().map(doc_json).collect()
}

fn doc_json(doc: &crate::core::project::project::DocumentEntry) -> serde_json::Value {
    serde_json::json!({
        "doc_id": doc.doc_id,
        "path": doc.path,
        "source_path": doc.source_path,
        "doc_type": doc.doc_type,
        "title": doc.title,
        "indexed": doc.indexed,
        "folder": doc.folder,
        "added_at": doc.added_at,
        "hash": doc.hash,
        "mtime": doc.mtime,
        "inspector_status": doc.inspector_status,
        "text_status": doc.text_status,
        "ocr_status": doc.ocr_status,
        "ocr_hash": doc.ocr_hash,
        "moldet_status": doc.moldet_status,
        "moldet_pages": doc.moldet_pages,
        "index_status": doc.index_status,
    })
}

fn project_json(project: &crate::core::project::Project) -> serde_json::Value {
    // Response shape must match the TS `ProjectResponse` contract in
    // `frontend/src/api/tauri/project.ts`:
    //   { success: boolean, project: { name, root, document_count }, error?: string }
    // The full document list comes via `scan_project_files` / `list_project_documents`,
    // not via `open_project`, so we only return the count here.
    let documents = project.list_documents().to_vec();
    serde_json::json!({
        "success": true,
        "project": {
            "name": project.root.file_name().map(|n| n.to_string_lossy().to_string()).unwrap_or_default(),
            "root": project.root.to_string_lossy().to_string(),
            "document_count": documents.len(),
        },
    })
}

/// 列出项目中的所有文档。
#[tauri::command]
pub fn list_project_documents(root: String) -> Result<serde_json::Value, String> {
    let root = clean_path(&root);
    let path = PathBuf::from(&root);
    let project = crate::core::project::Project::open(&path).ok_or_else(|| {
        AppError::new(ErrorCode::ProjectOpen, format!("项目不存在: {root}")).to_string()
    })?;

    let docs = project.list_documents().to_vec();
    Ok(serde_json::json!({
        "success": true,
        "documents": docs_json(&docs),
    }))
}

/// 列出项目中的所有文档，并附带每个文档的「读取完成」状态。
///
/// 完成判定：`<project_root>/projects/<doc_id>/text.md` 与 `report.md`
/// **都**存在。任一缺失视为「未完成读取」，需要重跑 `process_document`。
///
/// 该命令替代 `list_project_documents` 用于文档列表 UI — UI 应基于
/// `is_complete` 字段过滤/标记待处理文档，不要把它们当作已索引的。
#[tauri::command]
pub fn list_project_documents_with_status(root: String) -> Result<serde_json::Value, String> {
    let root = clean_path(&root);
    let path = PathBuf::from(&root);
    let project = crate::core::project::Project::open(&path).ok_or_else(|| {
        AppError::new(ErrorCode::ProjectOpen, format!("项目不存在: {root}")).to_string()
    })?;

    let docs: Vec<serde_json::Value> = project
        .list_documents()
        .iter()
        .map(|d| {
            let status = crate::parsers::pipeline::legacy::output::output_status(&path, &d.doc_id);
            let mut base = doc_json(d);
            base["is_complete"] = serde_json::Value::Bool(status.complete);
            base["incomplete_reason"] = serde_json::to_value(
                crate::parsers::pipeline::legacy::output::IncompleteReason::from_status(&status),
            )
            .unwrap_or(serde_json::Value::Null);
            base
        })
        .collect();

    Ok(serde_json::json!({
        "success": true,
        "documents": docs,
    }))
}

/// 查询单个文档的输出文件状态。
#[tauri::command]
pub fn get_document_output_status(
    root: String,
    doc_id: String,
) -> Result<serde_json::Value, String> {
    let root = clean_path(&root);
    let path = PathBuf::from(&root);
    let status = crate::parsers::pipeline::legacy::output::output_status(&path, &doc_id);
    Ok(serde_json::json!({
        "success": true,
        "doc_id": doc_id,
        "text_md_path": status.text_md_path,
        "text_md_exists": status.text_md_exists,
        "report_md_path": status.report_md_path,
        "report_md_exists": status.report_md_exists,
        "complete": status.complete,
        "incomplete_reason": crate::parsers::pipeline::legacy::output::IncompleteReason::from_status(&status),
    }))
}

/// 自动将所有未解析的 PDF 文档加入 ingest queue。
#[tauri::command]
pub async fn enqueue_unresolved_documents(root: String) -> Result<serde_json::Value, String> {
    let root = clean_path(&root);
    let path = PathBuf::from(&root);
    let project = crate::core::project::Project::open(&path).ok_or_else(|| {
        AppError::new(ErrorCode::ProjectOpen, format!("项目不存在: {root}")).to_string()
    })?;

    let queue = crate::core::document::ingest_queue::IngestQueue::new(&path)
        .map_err(|e| format!("打开处理队列失败: {e}"))?;

    let mut enqueued = 0usize;
    let mut skipped = 0usize;

    for doc in project.list_documents() {
        if doc.doc_type != "pdf" || doc.folder != "projects" {
            skipped += 1;
            continue;
        }
        if doc.index_status == "done" {
            skipped += 1;
            continue;
        }
        let Some(source_path) = project.get_document_source_path(&doc.doc_id) else {
            warn!("未找到文档 source_path: {}", doc.doc_id);
            skipped += 1;
            continue;
        };
        let source_str = source_path.to_string_lossy().to_string();

        match queue.contains_file(&source_str).await {
            Ok(true) => {
                skipped += 1;
                continue;
            }
            Ok(false) => {}
            Err(e) => {
                warn!("contains_file 检查失败 {}: {}", source_str, e);
            }
        }

        match queue
            .enqueue_with_stage(source_str, doc.doc_id.clone(), "inspector", false)
            .await
        {
            Ok(_) => enqueued += 1,
            Err(e) => {
                warn!("入队失败 {}: {}", doc.doc_id, e);
                skipped += 1;
            }
        }
    }

    Ok(serde_json::json!({
        "success": true,
        "enqueued": enqueued,
        "skipped": skipped,
    }))
}

#[derive(Debug, serde::Serialize, serde::Deserialize)]
struct FileNode {
    name: String,
    path: String,
    is_dir: bool,
    children: Vec<FileNode>,
}

fn build_file_tree(root: &std::path::Path) -> Vec<FileNode> {
    let mut result = Vec::new();
    let entries = match std::fs::read_dir(root) {
        Ok(entries) => entries,
        Err(e) => {
            warn!("Failed to read directory {}: {}", root.display(), e);
            return result;
        }
    };

    let mut entries: Vec<_> = entries.filter_map(|e| e.ok()).collect();
    entries.sort_by_key(|e| e.file_name());

    for entry in entries {
        let name = entry.file_name().to_string_lossy().to_string();
        if name.starts_with('.') || name == ".mbforge" {
            continue;
        }

        let path = entry.path();
        let is_dir = entry.file_type().map(|t| t.is_dir()).unwrap_or(false);

        if is_dir {
            let children = build_file_tree(&path);
            result.push(FileNode {
                name,
                path: path.to_string_lossy().to_string(),
                is_dir: true,
                children,
            });
        } else {
            result.push(FileNode {
                name,
                path: path.to_string_lossy().to_string(),
                is_dir: false,
                children: vec![],
            });
        }
    }

    result
}

/// 获取项目文件树（递归列出项目根目录下的文件和目录，排除隐藏文件和 .mbforge 元数据目录）。
#[tauri::command]
pub fn get_file_tree(root: String) -> Result<serde_json::Value, String> {
    let root = clean_path(&root);
    let path = PathBuf::from(&root);

    let project = crate::core::project::Project::open(&path).ok_or_else(|| {
        AppError::new(ErrorCode::ProjectOpen, format!("项目不存在: {root}")).to_string()
    })?;

    let tree = build_file_tree(&project.root);
    Ok(serde_json::json!({
        "success": true,
        "tree": tree,
    }))
}

/// 启动或重启当前项目的 ingest worker。
fn start_or_restart_ingest_worker(app: &tauri::AppHandle, project_root: &std::path::Path) {
    use crate::core::document::ingest_worker::{IngestWorker, IngestWorkerState};

    if let Some(state) = app.try_state::<IngestWorkerState>() {
        let mut guard = state.worker.lock().unwrap();
        if let Some(worker) = guard.take() {
            worker.stop();
        }
        let worker = IngestWorker::start(project_root.to_path_buf(), app.clone());
        *guard = Some(worker);
        log::info!(
            "[project_ops] ingest worker started for {}",
            project_root.display()
        );
    } else {
        log::warn!("[project_ops] IngestWorkerState not managed, cannot start worker");
    }
}
