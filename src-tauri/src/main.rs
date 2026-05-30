// Prevents additional console window on Windows in release
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod commands;
mod core;
mod parsers;

use commands::agent::AgentState;
use commands::molecule::MolDbState;

use std::process::{Command, Stdio};
use tauri::Manager;

struct BackendProcess(std::sync::Mutex<std::process::Child>);

fn main() {
    // Load .env from project root (dev mode) or app directory
    let _ = dotenvy::dotenv();

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(AgentState::new())
        .manage(MolDbState::new())
        .invoke_handler(tauri::generate_handler![
            commands::pdf::classify_pdf,
            commands::pdf::extract_text,
            commands::text_ops::text_chunk,
            commands::classifier::classify_page,
            commands::classifier::classify_document,
            commands::extractor::extract_esmiles_candidates,
            commands::extractor::extract_activities,
            commands::extractor::extract_associated_molecules,
            commands::agent::agent_init,
            commands::agent::agent_create_session,
            commands::agent::agent_chat,
            commands::agent::agent_chat_stream,
            commands::agent::agent_switch_project,
            commands::agent::agent_clear,
            commands::agent::agent_destroy_session,
            commands::agent::agent_get_history,
            parsers::pipeline::parse_pdf,
            parsers::pipeline::post_process_pdf,
            parsers::pipeline::process_document,
            commands::molecule::mol_init,
            commands::molecule::mol_add_relation,
            commands::molecule::mol_delete_relation,
            commands::molecule::mol_get_relation,
            commands::molecule::mol_find_by_molecule,
            commands::molecule::mol_find_similar,
            commands::molecule::mol_find_same_as,
            commands::molecule::mol_get_stats,
            commands::molecule::mol_assign_cluster,
            commands::molecule::mol_remove_from_cluster,
            commands::molecule::mol_get_cluster_members,
            commands::molecule::mol_get_molecule_clusters,
            commands::molecule::mol_list_clusters,
            commands::molecule::mol_find_analogs_with_activity,
            commands::molecule::mol_scaffold_profile,
            commands::molecule::mol_find_activity_cliffs,
            commands::molecule::mol_dedup_batch,
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
            let no_spawn = std::env::var("MBFORGE_NO_SPAWN").unwrap_or_default().trim() == "1";
            let server_script = resource_dir.join("src").join("mbforge").join("model_server").join("main.py");
            let mut cmd = Command::new(&python);

            if !no_spawn && server_script.exists() {
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
