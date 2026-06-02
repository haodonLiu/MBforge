// Prevents additional console window on Windows in release
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod commands;
mod core;
mod parsers;
mod sidecar;


use commands::agent::AgentState;
use commands::mol_engine::MoleculeEngineState;

use std::process::Command;
use tauri::Manager;

fn load_dotenv() {
    if let Ok(contents) = std::fs::read_to_string(".env") {
        for line in contents.lines() {
            let line = line.trim();
            if line.is_empty() || line.starts_with('#') { continue; }
            if let Some((key, value)) = line.split_once('=') {
                let k = key.trim();
                let v = value.trim().trim_matches('"').trim_matches('\'');
                if !k.is_empty() {
                    std::env::set_var(k, v);
                }
            }
        }
    }
}

fn main() {
    load_dotenv();

    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_shell::init())
        .manage(AgentState::new())
        .manage(MoleculeEngineState::new())
        .invoke_handler(commands::handler())
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
            let no_spawn = std::env::var("MBFORGE_NO_SPAWN")
                .unwrap_or_default()
                .trim()
                == "1";
            let server_script = resource_dir
                .join("src")
                .join("mbforge")
                .join("model_server")
                .join("main.py");

            if !no_spawn && server_script.exists() {
                // 写入模型路径供 Python sidecar 读取（单一真相源在 Rust 侧）
                core::resource_manager::write_resolved_paths();

                let sidecar = sidecar::SidecarInner::new(python, resource_dir);
                if let Err(e) = sidecar::spawn_and_start_readers(&sidecar, &app_handle) {
                    eprintln!("[tauri] Failed to start sidecar: {}", e);
                } else {
                    app.manage(sidecar.clone());
                    sidecar::start_health_monitor(sidecar, app_handle.clone());
                }
            } else if !no_spawn {
                #[cfg(debug_assertions)]
                eprintln!("[tauri] Dev mode: Python server expected to run separately");
            }

            Ok(())
        })
        .on_window_event(|app, event| {
            if let tauri::WindowEvent::Destroyed = event {
                if let Some(state) = app.try_state::<std::sync::Arc<sidecar::SidecarInner>>() {
                    let mut child = state.child.lock().unwrap();
                    if let Some(ref mut c) = *child {
                        let _ = c.kill();
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
