#![allow(dead_code)]
use std::path::PathBuf;

use tauri::AppHandle;
use tauri_plugin_dialog::DialogExt;

use crate::core::error::{AppError, AppResult, ErrorCode};
use crate::core::helpers::{assert_within_root, clean_path};
use crate::core::project::project::DocumentEntry;

fn wrap<T>(result: AppResult<T>) -> Result<T, String> {
    result.map_err(|e| e.to_string())
}

fn resolve_path(project_root: &str) -> Result<PathBuf, AppError> {
    let root = clean_path(project_root);
    if root.is_empty() {
        return Err(AppError::new(ErrorCode::ProjectOpen, "项目根路径为空"));
    }
    Ok(PathBuf::from(root))
}

/// 使用系统文件选择器导入文件到项目目录。
///
/// 弹出对话框让用户选择文件，然后添加到项目索引。PDF 文件会自动创建为
/// 独立的 DocumentProject（`projects/<doc_id>/source.pdf`）。非 PDF 文件仍
/// 复制到项目根目录并按路径索引。
#[tauri::command]
pub async fn upload_files(
    app: AppHandle,
    project_root: String,
) -> Result<Vec<DocumentEntry>, String> {
    let root_path = wrap(resolve_path(&project_root))?;

    let mut project =
        crate::core::project::project::Project::open(&root_path).ok_or_else(|| {
            AppError::new(
                ErrorCode::ProjectOpen,
                format!("项目不存在: {}", root_path.display()),
            )
            .with_path(root_path.to_string_lossy())
            .to_string()
        })?;

    let (tx, rx) = tokio::sync::oneshot::channel();
    app.dialog()
        .file()
        .add_filter(
            "Documents",
            &[
                "pdf", "md", "txt", "sdf", "mol", "mol2", "pdb", "smi", "csv", "json", "xlsx",
            ],
        )
        .add_filter("All Files", &["*"])
        .pick_files(move |files| {
            let _ = tx.send(files);
        });

    let file_paths = rx
        .await
        .map_err(|_| AppError::new(ErrorCode::TauriInvoke, "对话框通道关闭").to_string())?
        .ok_or_else(|| AppError::new(ErrorCode::TauriInvoke, "未选择文件").to_string())?;

    let mut entries = Vec::new();
    for fp in file_paths {
        let src = fp
            .into_path()
            .map_err(|_| AppError::new(ErrorCode::FileRead, "无效文件路径").to_string())?;

        if !src.exists() {
            log::warn!("Selected file does not exist: {:?}", src);
            continue;
        }

        let name = src
            .file_name()
            .and_then(|n| n.to_str())
            .unwrap_or("unknown");

        // PDFs become isolated DocumentProjects; other files are copied to root.
        let ext = src
            .extension()
            .and_then(|e| e.to_str())
            .unwrap_or("")
            .to_lowercase();

        if ext != "pdf" {
            let dest = project.root.join(name);

            // 路径遍历安全检查
            if let Err(e) = assert_within_root(&project.root.to_string_lossy(), &dest) {
                log::error!(
                    "Path traversal blocked: {:?} escapes {:?}: {}",
                    dest,
                    project.root,
                    e
                );
                continue;
            }

            tokio::fs::copy(&src, &dest).await.map_err(|e| {
                AppError::new(ErrorCode::FileWrite, format!("复制文件失败: {e}"))
                    .with_path(dest.to_string_lossy())
                    .to_string()
            })?;

            if let Some(entry) = project.add_file(&dest) {
                log::info!("Added file to project: {} -> {}", name, entry.doc_id);
                entries.push(entry);
            }
        } else if let Some(entry) = project.add_file(&src) {
            log::info!("Added PDF to project: {} -> {}", name, entry.doc_id);
            // 按设置决定是否自动入队处理。默认关闭，用户可手动触发。
            let config = crate::core::config::settings::AppConfig::load();
            if config.ingest.auto_enqueue_on_import {
                if let Ok(q) = crate::core::document::ingest_queue::IngestQueue::new(&project.root)
                {
                    let source_path = project
                        .root
                        .join(crate::core::constants::PROJECTS_DIR)
                        .join(&entry.doc_id)
                        .join(crate::core::constants::PROJECT_SOURCE_FILE);
                    let _ = q
                        .enqueue_with_stage(
                            source_path.to_string_lossy().to_string(),
                            entry.doc_id.clone(),
                            "inspector",
                        )
                        .await;
                }
            }
            entries.push(entry);
        }
    }

    Ok(entries)
}

/// 删除项目中的文件（物理删除 + 索引移除）。
///
/// 对于 PDF DocumentProject，会删除整个 `projects/<doc_id>/` 目录；
/// 对于非 PDF 根目录文件，仅删除物理文件。
#[tauri::command]
pub async fn delete_file(project_root: String, doc_id: String) -> Result<bool, String> {
    let root_path = wrap(resolve_path(&project_root))?;

    let mut project = crate::core::project::Project::open(&root_path).ok_or_else(|| {
        AppError::new(
            ErrorCode::ProjectOpen,
            format!("项目不存在: {}", root_path.display()),
        )
        .with_path(root_path.to_string_lossy())
        .to_string()
    })?;

    let entry = project.get_document(&doc_id).ok_or_else(|| {
        AppError::new(ErrorCode::FileNotFound, format!("文档未找到: {doc_id}")).to_string()
    })?;

    // For non-PDF legacy files, delete the physical file. PDFs are removed
    // via the DocumentProject directory in remove_document().
    if entry.doc_type != "pdf" {
        let full_path = project.root.join(&entry.path);
        if full_path.exists() {
            if let Err(e) = tokio::fs::remove_file(&full_path).await {
                log::error!("Failed to delete file {:?}: {}", full_path, e);
                return Err(
                    AppError::new(ErrorCode::FileWrite, format!("删除文件失败: {e}"))
                        .with_path(full_path.to_string_lossy())
                        .to_string(),
                );
            }
            log::info!("Deleted file: {:?}", full_path);
        } else {
            log::warn!("File already removed from disk: {:?}", full_path);
        }
    }

    project.remove_document(&doc_id);
    Ok(true)
}

/// 读取文本文件内容（UTF-8，异步不阻塞 UI）。
#[tauri::command]
pub async fn read_text_file(project_root: String, path: String) -> Result<String, String> {
    let path_buf = PathBuf::from(&path);
    if let Err(_e) = assert_within_root(&project_root, &path_buf) {
        return Err(AppError::new(ErrorCode::FilePermission, "路径越权访问")
            .with_path(path)
            .to_string());
    }
    if !path_buf.exists() {
        return Err(AppError::new(
            ErrorCode::FileNotFound,
            format!("文件不存在: {}", path_buf.display()),
        )
        .with_path(path)
        .to_string());
    }
    tokio::fs::read_to_string(&path_buf).await.map_err(|e| {
        AppError::new(ErrorCode::FileRead, format!("读取文件失败: {e}"))
            .with_path(path)
            .to_string()
    })
}

/// 使用系统默认程序打开文件。
#[tauri::command]
pub async fn open_file(project_root: String, path: String) -> Result<(), String> {
    let path_buf = PathBuf::from(&path);
    if let Err(_e) = assert_within_root(&project_root, &path_buf) {
        return Err(AppError::new(ErrorCode::FilePermission, "路径越权访问")
            .with_path(path)
            .to_string());
    }

    if !path_buf.exists() {
        log::error!("open_file: file not found: {}", path);
        return Err(AppError::new(
            ErrorCode::FileNotFound,
            format!("文件不存在: {}", path_buf.display()),
        )
        .with_path(path)
        .to_string());
    }

    log::info!("open_file: {}", path);

    #[cfg(target_os = "windows")]
    {
        let path_str = path_buf.to_string_lossy();
        std::process::Command::new("rundll32.exe")
            .args(["url.dll,FileProtocolHandler", &path_str])
            .spawn()
            .or_else(|_| {
                std::process::Command::new("cmd")
                    .args(["/C", "start", "", &path_str])
                    .spawn()
            })
            .map_err(|e| {
                log::error!("open_file failed for path={}: {}", path, e);
                AppError::new(ErrorCode::FileWrite, format!("打开文件失败: {e}")).to_string()
            })?;
    }

    #[cfg(target_os = "macos")]
    {
        std::process::Command::new("open")
            .arg(&path_buf)
            .spawn()
            .map_err(|e| {
                log::error!("open_file open failed for path={}: {}", path, e);
                AppError::new(ErrorCode::FileWrite, format!("打开文件失败: {e}")).to_string()
            })?;
    }

    #[cfg(target_os = "linux")]
    {
        std::process::Command::new("xdg-open")
            .arg(&path_buf)
            .spawn()
            .map_err(|e| {
                log::error!("open_file xdg-open failed for path={}: {}", path, e);
                AppError::new(ErrorCode::FileWrite, format!("打开文件失败: {e}")).to_string()
            })?;
    }

    Ok(())
}
