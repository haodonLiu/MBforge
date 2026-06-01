// Prevents additional console window on Windows in release
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod commands;
mod core;
mod parsers;
mod sidecar;


use commands::agent::AgentState;
use commands::molecule::MolDbState;
use commands::mol_store::MolStoreState;

use std::process::Command;
use tauri::Manager;

fn main() {
    // Load .env from project root (dev mode) or app directory
    let _ = dotenvy::dotenv();

    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_shell::init())
        .manage(AgentState::new())
        .manage(MolDbState::new())
        .manage(MolStoreState::new())
        .invoke_handler(tauri::generate_handler![
            commands::file_ops::open_file,
            commands::file_ops::read_text_file,
            commands::file_ops::upload_files,
            commands::file_ops::delete_file,
            commands::project_ops::open_project,
            commands::project_ops::scan_project_files,
            commands::project_ops::list_project_documents,
            commands::project_ops::get_file_tree,
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
            parsers::pipeline::index_project_rust,
            core::knowledge_base::kb_search,
            core::knowledge_base::kb_search_stream,
            core::knowledge_base::kb_get_structure,
            core::knowledge_base::kb_get_pages,
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
            // Molecule store commands
            commands::mol_store::mol_store_init,
            commands::mol_store::mol_store_add,
            commands::mol_store::mol_store_list,
            commands::mol_store::mol_store_get,
            commands::mol_store::mol_store_search,
            commands::mol_store::mol_store_delete,
            commands::mol_store::mol_store_stats,
            commands::mol_store::mol_store_search_by_smiles,
            commands::mol_store::mol_store_list_by_doc,
            commands::sidecar::sidecar_status,
            commands::sidecar::sidecar_restart,
            // 资源管理
            core::resource_manager::resources_check,
            core::resource_manager::resources_status,
            core::resource_manager::resources_get_model_path,
            core::resource_manager::resources_catalog,
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
