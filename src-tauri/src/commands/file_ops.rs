use std::path::PathBuf;

use tauri::AppHandle;
use tauri_plugin_dialog::DialogExt;

use crate::core::project::DocumentEntry;

/// 去掉 Windows 长路径前缀 `\\?\`
fn clean_path(raw: &str) -> String {
    if cfg!(windows) {
        raw.trim_start_matches(r"\\?\").to_string()
    } else {
        raw.to_string()
    }
}

/// 使用系统文件选择器导入文件到项目目录。
///
/// 弹出对话框让用户选择文件，然后将文件复制到项目根目录并更新索引。
#[tauri::command]
pub async fn upload_files(
    app: AppHandle,
    project_root: String,
) -> Result<Vec<DocumentEntry>, String> {
    let root = clean_path(&project_root);
    let root_path = PathBuf::from(&root);

    let mut project = crate::core::project::Project::open(&root_path)
        .ok_or_else(|| format!("Project not found: {}", root))?;

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
        .pick_files(move |files| { let _ = tx.send(files); });

    let file_paths = rx.await
        .map_err(|_| "Dialog channel closed".to_string())?
        .ok_or_else(|| "No files selected".to_string())?;

    let mut entries = Vec::new();
    for fp in file_paths {
        let src = fp.into_path()
            .map_err(|_| "Invalid file path".to_string())?;

        if !src.exists() {
            log::warn!("Selected file does not exist: {:?}", src);
            continue;
        }

        let name = src
            .file_name()
            .and_then(|n| n.to_str())
            .unwrap_or("unknown");
        let dest = project.root.join(name);

        // 路径遍历安全检查
        let root_canon = project
            .root
            .canonicalize()
            .unwrap_or_else(|_| project.root.clone());
        let dest_canon = dest.canonicalize().unwrap_or_else(|_| dest.clone());
        if !dest_canon.starts_with(&root_canon) {
            log::error!(
                "Path traversal blocked: {:?} escapes {:?}",
                dest,
                project.root
            );
            continue;
        }

        std::fs::copy(&src, &dest)
            .map_err(|e| format!("Failed to copy '{}': {}", name, e))?;

        if let Some(entry) = project.add_file(&dest) {
            log::info!("Added file to project: {} -> {}", name, entry.doc_id);
            entries.push(entry);
        }
    }

    Ok(entries)
}

/// 删除项目中的文件（物理删除 + 索引移除）。
#[tauri::command]
pub async fn delete_file(project_root: String, doc_id: String) -> Result<bool, String> {
    let root = clean_path(&project_root);
    let root_path = PathBuf::from(&root);

    let mut project = crate::core::project::Project::open(&root_path)
        .ok_or_else(|| format!("Project not found: {}", root))?;

    let entry = project
        .get_document(&doc_id)
        .ok_or_else(|| format!("Document not found: {}", doc_id))?;

    let full_path = project.root.join(&entry.path);
    if full_path.exists() {
        if let Err(e) = std::fs::remove_file(&full_path) {
            log::error!("Failed to delete file {:?}: {}", full_path, e);
            return Err(format!("Failed to delete file: {}", e));
        }
        log::info!("Deleted file: {:?}", full_path);
    } else {
        log::warn!("File already removed from disk: {:?}", full_path);
    }

    project.remove_document(&doc_id);
    Ok(true)
}

/// 使用系统默认程序打开文件。
#[tauri::command]
pub async fn open_file(path: String) -> Result<(), String> {
    let path_buf = PathBuf::from(&path);

    if !path_buf.exists() {
        log::error!("open_file: file not found: {}", path);
        return Err(format!("File not found: {:?}", path_buf));
    }

    log::info!("open_file: {}", path);

    #[cfg(target_os = "windows")]
    {
        std::process::Command::new("cmd")
            .args(["/C", "start", "", &path_buf.to_string_lossy()])
            .spawn()
            .map_err(|e| {
                log::error!("open_file cmd start failed for path={}: {}", path, e);
                format!("Failed to open file: {}", e)
            })?;
    }

    #[cfg(target_os = "macos")]
    {
        std::process::Command::new("open")
            .arg(&path_buf)
            .spawn()
            .map_err(|e| {
                log::error!("open_file open failed for path={}: {}", path, e);
                format!("Failed to open file: {}", e)
            })?;
    }

    #[cfg(target_os = "linux")]
    {
        std::process::Command::new("xdg-open")
            .arg(&path_buf)
            .spawn()
            .map_err(|e| {
                log::error!("open_file xdg-open failed for path={}: {}", path, e);
                format!("Failed to open file: {}", e)
            })?;
    }

    Ok(())
}
