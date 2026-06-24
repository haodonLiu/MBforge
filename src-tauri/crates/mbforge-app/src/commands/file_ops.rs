#![allow(dead_code)]
use std::path::PathBuf;

use tauri::AppHandle;
use tauri_plugin_dialog::DialogExt;

use mbforge_domain::project::project::DocumentEntry;
use mbforge_infra::error::{AppError, AppResult, ErrorCode};
use mbforge_infra::helpers::{assert_within_root, clean_path};

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
        mbforge_domain::project::project::Project::open(&root_path).ok_or_else(|| {
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
            let config = mbforge_infra::config::settings::AppConfig::load();
            if config.ingest.auto_enqueue_on_import {
                if let Ok(q) = mbforge_domain::ingest_queue::IngestQueue::new(&project.root) {
                    let source_path = project
                        .root
                        .join(mbforge_infra::config::constants::PROJECTS_DIR)
                        .join(&entry.doc_id)
                        .join(mbforge_infra::config::constants::PROJECT_SOURCE_FILE);
                    let _ = q
                        .enqueue_with_stage(
                            source_path.to_string_lossy().to_string(),
                            entry.doc_id.clone(),
                            "inspector",
                            false,
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

    let mut project = mbforge_domain::project::Project::open(&root_path).ok_or_else(|| {
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

/// 彻底删除 PDF 文档及其所有派生数据。
#[tauri::command]
pub async fn project_delete_document(project_root: String, doc_id: String) -> Result<(), String> {
    let root_path = wrap(resolve_path(&project_root))?;

    let mut project = mbforge_domain::project::Project::open(&root_path).ok_or_else(|| {
        AppError::new(
            ErrorCode::ProjectOpen,
            format!("项目不存在: {}", root_path.display()),
        )
        .with_path(root_path.to_string_lossy())
        .to_string()
    })?;

    project
        .delete_document(&doc_id)
        .map_err(|e| AppError::new(ErrorCode::FileWrite, format!("删除文档失败: {e}")).to_string())
}

/// 重新读取已有 PDF：保留源文件，清空所有抽取结果后重新入队。
#[tauri::command]
pub async fn project_reingest_document(project_root: String, doc_id: String) -> Result<(), String> {
    let root_path = wrap(resolve_path(&project_root))?;

    let mut project = mbforge_domain::project::Project::open(&root_path).ok_or_else(|| {
        AppError::new(
            ErrorCode::ProjectOpen,
            format!("项目不存在: {}", root_path.display()),
        )
        .with_path(root_path.to_string_lossy())
        .to_string()
    })?;

    let source_path = project.get_document_source_path(&doc_id).ok_or_else(|| {
        AppError::new(
            ErrorCode::FileNotFound,
            format!("文档源文件未找到: {doc_id}"),
        )
        .to_string()
    })?;

    project.reingest_document(&doc_id).map_err(|e| {
        AppError::new(ErrorCode::FileWrite, format!("重新读取文档失败: {e}")).to_string()
    })?;

    let queue = mbforge_domain::ingest_queue::IngestQueue::new(&project.root).map_err(|e| {
        AppError::new(ErrorCode::QueueFull, format!("打开处理队列失败: {e}")).to_string()
    })?;

    let file_path = source_path.to_string_lossy().to_string();
    queue
        .enqueue_with_stage(file_path, doc_id.clone(), "inspector", true)
        .await
        .map_err(|e| format!("重新入队失败: {e}"))?;

    Ok(())
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

/// Open an external URL in the system default browser.
///
/// Frontend cannot use `window.open` reliably inside a Tauri webview
/// (the new tab is either blocked or replaced by the existing window
/// depending on version). This command delegates to the OS launcher
/// (`cmd /C start` on Windows, `open` on macOS, `xdg-open` on Linux)
/// so the user's default browser picks up the URL.
#[tauri::command]
pub async fn open_external_url(url: String) -> Result<(), String> {
    if !(url.starts_with("http://") || url.starts_with("https://")) {
        return Err(format!(
            "open_external_url: refusing non-http(s) URL: {url}"
        ));
    }
    log::info!("open_external_url: {url}");

    #[cfg(target_os = "windows")]
    {
        std::process::Command::new("cmd")
            .args(["/C", "start", "", &url])
            .spawn()
            .map_err(|e| format!("open_external_url failed: {e}"))?;
    }
    #[cfg(target_os = "macos")]
    {
        std::process::Command::new("open")
            .arg(&url)
            .spawn()
            .map_err(|e| format!("open_external_url failed: {e}"))?;
    }
    #[cfg(target_os = "linux")]
    {
        std::process::Command::new("xdg-open")
            .arg(&url)
            .spawn()
            .map_err(|e| format!("open_external_url failed: {e}"))?;
    }
    Ok(())
}
