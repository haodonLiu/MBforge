// Prevents additional console window on Windows in release
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod commands;
use log::error;
mod core;
mod parsers;
mod protocol;
mod sidecar;

use commands::agent::AgentState;
use commands::mol_engine::MoleculeEngineState;

use std::process::Command;
use tauri::Manager;

fn load_dotenv() {
    // Walk up from CWD looking for the first `.env` we can read.
    // Dev mode runs the binary from `src-tauri/target/...`, so CWD-relative
    // `.env` would miss the project-root copy. Search ancestors instead.
    let mut dir: Option<&std::path::Path> = Some(std::path::Path::new("."));
    let mut found: Option<std::path::PathBuf> = None;
    for _ in 0..6 {
        let Some(d) = dir else { break };
        let candidate = d.join(".env");
        if candidate.is_file() {
            found = Some(candidate);
            break;
        }
        dir = d.parent();
    }
    let Some(path) = found else {
        log::debug!("[tauri] .env not found in cwd or ancestors; using process env only");
        return;
    };
    log::info!("[tauri] loading .env from {}", path.display());
    if let Ok(contents) = std::fs::read_to_string(&path) {
        for line in contents.lines() {
            let line = line.trim();
            if line.is_empty() || line.starts_with('#') {
                continue;
            }
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

    // Ctrl-C / SIGTERM 时主动 kill Python sidecar 子进程。
    // 没这步，terminal 按 Ctrl-C 时 Tauri 进程直接死，spawn 出来的 uvicorn
    // 变孤儿继续跑，下次 `cargo tauri dev` 会撞 "address already in use"。
    sidecar::install_signal_handler();

    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_shell::init())
        .register_asynchronous_uri_scheme_protocol("mbforge", protocol::handle_mbforge_request)
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

            let python = py_paths
                .iter()
                .find(|p| {
                    if p.is_absolute() {
                        p.exists()
                    } else {
                        Command::new(p).arg("--version").output().is_ok()
                    }
                })
                .cloned()
                .unwrap_or_else(|| std::path::PathBuf::from("python"));

            // Start model server
            let no_spawn = std::env::var("MBFORGE_NO_SPAWN").unwrap_or_default().trim() == "1";

            // 生产模式路径（打包后资源目录内）
            let prod_script = resource_dir
                .join("src")
                .join("mbforge")
                .join("model_server")
                .join("main.py");

            // 开发模式路径探测：CARGO_MANIFEST_DIR 指向 src-tauri/，项目根目录是其父目录
            let dev_paths = std::env::var("CARGO_MANIFEST_DIR").ok().and_then(|manifest| {
                let manifest_path = std::path::PathBuf::from(manifest);
                let project_root = manifest_path.parent()?.to_path_buf();
                let script = project_root.join("src").join("mbforge").join("model_server").join("main.py");
                if script.exists() {
                    Some((script, project_root))
                } else {
                    None
                }
            });

            let (server_script, working_dir) = if prod_script.exists() {
                (prod_script, resource_dir)
            } else if let Some((script, root)) = dev_paths {
                (script, root)
            } else {
                (prod_script, resource_dir)
            };

            if !no_spawn && server_script.exists() {
                // 写入模型路径供 Python sidecar 读取（单一真相源在 Rust 侧）
                core::resource_manager::write_resolved_paths();

                let sidecar = sidecar::SidecarInner::new(python, working_dir);
                if let Err(e) = sidecar::spawn_and_start_readers(&sidecar, &app_handle) {
                    log::error!("[tauri] Failed to start sidecar: {}", e);
                } else {
                    app.manage(sidecar.clone());
                    sidecar::start_health_monitor(sidecar, app_handle.clone());
                }
            } else if !no_spawn {
                #[cfg(debug_assertions)]
                log::warn!("[tauri] Dev mode: Python server script not found at {}", server_script.display());
            }

            Ok(())
        })
        .on_window_event(|app, event| {
            if let tauri::WindowEvent::Destroyed = event {
                if let Some(state) = app.try_state::<std::sync::Arc<sidecar::SidecarInner>>() {
                    let mut child = state.child.lock().unwrap_or_else(|e| e.into_inner());
                    if let Some(ref mut c) = *child {
                        let _ = c.kill();
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
