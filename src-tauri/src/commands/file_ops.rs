use tauri::AppHandle;
use tauri_plugin_shell::ShellExt;

/// Open a file with the system's default application
#[tauri::command]
pub async fn open_file(path: String) -> Result<(), String> {
    let path_buf = std::path::PathBuf::from(&path);

    if !path_buf.exists() {
        log::error!("open_file: file not found: {}", path);
        return Err(format!("File not found: {:?}", path_buf));
    }

    log::info!("open_file: {}", path);

    // Use shell to open with default application
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
