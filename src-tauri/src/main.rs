// Prevents additional console window on Windows in release
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod commands;
mod core;
mod parsers;
mod protocol;
mod sidecar;

use commands::mol_engine::MoleculeEngineState;
use core::document::ingest_worker::{IngestWorker, IngestWorkerState};

use crate::core::helpers::LockResultExt;
use std::process::Command;
use tauri::Manager;

fn load_dotenv() {
    // Walk up from CWD looking for the first `.env` we can read.
    // Dev mode runs the binary from `src-tauri/target/...`, so CWD-relative
    // `.env` would miss the project-root copy. Search ancestors instead.
    //
    // Canonicalize first — `Path::new(".").parent()` returns `Some("")` (not
    // a real parent), so a naive `dir = d.parent()` loop never walks up. We
    // need an absolute path before `.parent()` actually moves us toward `/`.
    let start = std::env::current_dir()
        .ok()
        .and_then(|p| p.canonicalize().ok());
    let mut dir: Option<std::path::PathBuf> = start;
    let mut found: Option<std::path::PathBuf> = None;
    for _ in 0..8 {
        let Some(d) = dir.as_deref() else { break };
        let candidate = d.join(".env");
        if candidate.is_file() {
            found = Some(candidate);
            break;
        }
        dir = d.parent().map(|p| p.to_path_buf());
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
        .manage(MoleculeEngineState::new())
        .manage(IngestWorkerState::default())
        .manage(crate::core::project::resource_manager::DownloadManagerState::default())
        .invoke_handler(commands::handler())
        .setup(|app| {
            let app_handle = app.handle();
            let resource_dir = app_handle.path().resource_dir().unwrap_or_default();

            // 开发模式路径探测：CARGO_MANIFEST_DIR 指向 src-tauri/，项目根目录是其父目录
            let dev_paths = std::env::var("CARGO_MANIFEST_DIR")
                .ok()
                .and_then(|manifest| {
                    let manifest_path = std::path::PathBuf::from(manifest);
                    let project_root = manifest_path.parent()?.to_path_buf();
                    let script = project_root.join("src").join("mbforge").join("server.py");
                    if script.exists() {
                        Some((script, project_root.clone()))
                    } else {
                        None
                    }
                });

            // Try to find Python backend.
            // In dev mode, prefer the project's virtual environment so that
            // uv-managed dependencies (ultralytics, transformers, etc.) are available.
            #[cfg(target_os = "windows")]
            let venv_python =
                |root: &std::path::Path| root.join(".venv").join("Scripts").join("python.exe");
            #[cfg(not(target_os = "windows"))]
            let venv_python =
                |root: &std::path::Path| root.join(".venv").join("bin").join("python");

            let mut py_paths: Vec<std::path::PathBuf> = Vec::new();
            if let Some((_, ref project_root)) = dev_paths {
                if let Ok(uv_venv) = std::env::var("UV_VIRTUAL_ENV") {
                    py_paths.push(std::path::PathBuf::from(uv_venv).join(
                        if cfg!(target_os = "windows") {
                            "Scripts/python.exe"
                        } else {
                            "bin/python"
                        },
                    ));
                }
                py_paths.push(venv_python(project_root));
            }
            py_paths.extend([
                resource_dir.join("python.exe"),
                resource_dir.join("python").join("python.exe"),
                std::path::PathBuf::from("python"),
                std::path::PathBuf::from("python3"),
            ]);

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
            let prod_script = resource_dir.join("src").join("mbforge").join("server.py");

            let (server_script, working_dir) = if prod_script.exists() {
                (prod_script, resource_dir)
            } else if let Some((script, root)) = dev_paths {
                (script, root)
            } else {
                (prod_script, resource_dir)
            };

            if !no_spawn && server_script.exists() {
                // 写入模型路径供 Python sidecar 读取（单一真相源在 Rust 侧）
                core::project::resource_manager::write_resolved_paths();

                let sidecar = sidecar::SidecarInner::new(python, working_dir);
                if let Err(e) = sidecar::spawn_and_start_readers(&sidecar, &app_handle) {
                    log::error!("[tauri] Failed to start sidecar: {}", e);
                } else {
                    app.manage(sidecar.clone());

                    // 异步探活：把 SidecarClient 单例 + health() 接到启动序列，
                    // 让前端的"环境检测"按钮可以走同一份共享 client。
                    let health_client = core::sidecar_client::get_or_init();
                    match health_client {
                        Ok(client) => {
                            let client = std::sync::Arc::clone(&client);
                            tauri::async_runtime::spawn(async move {
                                match client.health().await {
                                    Ok(h) => log::info!("[sidecar] health: {:?}", h),
                                    Err(e) => log::warn!("[sidecar] health probe failed: {}", e),
                                }
                            });
                        }
                        Err(e) => log::warn!("[sidecar] client init failed: {}", e),
                    }
                    sidecar::start_health_monitor(sidecar, app_handle.clone());
                }
            } else if !no_spawn {
                #[cfg(debug_assertions)]
                log::warn!(
                    "[tauri] Dev mode: Python server script not found at {}",
                    server_script.display()
                );
            }

            // 启动 ingest worker（如环境变量指定了项目根目录）。
            if let Ok(project_root) = std::env::var("MBFORGE_PROJECT_ROOT") {
                let path = std::path::PathBuf::from(&project_root);
                if path.is_dir() {
                    let worker = IngestWorker::start(path, app_handle.clone());
                    if let Some(state) = app_handle.try_state::<IngestWorkerState>() {
                        *state.worker.lock().unwrap() = Some(worker);
                    }
                } else {
                    log::warn!(
                        "[tauri] MBFORGE_PROJECT_ROOT points to non-directory: {}",
                        project_root
                    );
                }
            }

            Ok(())
        })
        .on_window_event(|app, event| {
            if let tauri::WindowEvent::Destroyed = event {
                if let Some(state) = app.try_state::<std::sync::Arc<sidecar::SidecarInner>>() {
                    let mut child = state.child.lock().into_inner();
                    if let Some(ref mut c) = *child {
                        let _ = c.kill();
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
