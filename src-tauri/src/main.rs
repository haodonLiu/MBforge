// Prevents additional console window on Windows in release
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod commands;

use std::process::{Command, Stdio};
use tauri::Manager;

struct BackendProcess(std::sync::Mutex<std::process::Child>);

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .invoke_handler(tauri::generate_handler![
            commands::pdf::classify_pdf,
            commands::pdf::extract_text,
        ])
        .setup(|app| {
            let app_handle = app.handle();
            let resource_dir = app_handle.path().resource_dir().unwrap_or_default();

            // Try to find Python backend
            let py_paths = [
                resource_dir.join("python.exe"),
                resource_dir.join("python").join("python.exe"),
                std::path::PathBuf::from("python"),
                std::path::PathBuf::from("python3"),
            ];

            let python = py_paths.iter().find(|p| {
                if p.is_absolute() {
                    p.exists()
                } else {
                    Command::new(p).arg("--version").output().is_ok()
                }
            }).cloned().unwrap_or_else(|| std::path::PathBuf::from("python"));

            // Start model server
            let server_script = resource_dir.join("src").join("mbforge").join("model_server").join("main.py");
            let mut cmd = Command::new(&python);

            if server_script.exists() {
                cmd.arg("-m").arg("uvicorn")
                    .arg("mbforge.model_server.main:app")
                    .arg("--host").arg("127.0.0.1")
                    .arg("--port").arg("18792")
                    .current_dir(resource_dir);
            } else {
                // Development: assume backend is running separately
                eprintln!("[tauri] Model server script not found, assuming dev mode");
                return Ok(());
            }

            let child = cmd
                .stdout(Stdio::piped())
                .stderr(Stdio::piped())
                .spawn()
                .map_err(|e| {
                    eprintln!("[tauri] Failed to start backend: {}", e);
                    e
                })
                .ok();

            if let Some(c) = child {
                app.manage(BackendProcess(std::sync::Mutex::new(c)));
            }

            Ok(())
        })
        .on_window_event(|app, event| {
            if let tauri::WindowEvent::Destroyed = event {
                if let Some(state) = app.try_state::<BackendProcess>() {
                    let mut child = state.0.lock().unwrap();
                    let _ = child.kill();
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
