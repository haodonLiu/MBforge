pub mod agent;
pub mod classifier;
pub mod extractor;
pub mod file_ops;
pub mod mol_engine;
pub mod mol_store;
pub mod molecule;
pub mod notes;
pub mod pdf;
pub mod project_ops;
pub mod sidecar;
pub mod text_ops;

/// 返回 Tauri invoke handler，聚合所有命令模块的 IPC 函数。
///
/// 新增命令时，只需在对应模块中定义 `#[tauri::command]` 函数，
/// 然后在此列表的对应分组中追加一行即可；`main.rs` 无需修改。
pub fn handler() -> impl Fn(tauri::ipc::Invoke<tauri::Wry>) -> bool + Send + Sync + 'static {
    tauri::generate_handler![
        // file_ops
        file_ops::open_file,
        file_ops::read_text_file,
        file_ops::upload_files,
        file_ops::delete_file,
        // project_ops
        project_ops::open_project,
        project_ops::scan_project_files,
        project_ops::list_project_documents,
        project_ops::get_file_tree,
        // pdf
        pdf::classify_pdf,
        pdf::extract_text,
        // text_ops
        text_ops::text_chunk,
        // classifier
        classifier::classify_page,
        classifier::classify_document,
        // extractor
        extractor::extract_esmiles_candidates,
        extractor::extract_activities,
        extractor::extract_associated_molecules,
        // agent
        agent::agent_init,
        agent::agent_create_session,
        agent::agent_chat,
        agent::agent_chat_stream,
        agent::agent_switch_project,
        agent::agent_clear,
        agent::agent_destroy_session,
        agent::agent_get_history,
        // parsers
        crate::parsers::pipeline::parse_pdf,
        crate::parsers::pipeline::post_process_pdf,
        crate::parsers::pipeline::process_document,
        crate::parsers::pipeline::index_project_rust,
        // knowledge_base
        crate::core::knowledge_base::kb_search,
        crate::core::knowledge_base::kb_search_stream,
        crate::core::knowledge_base::kb_get_structure,
        crate::core::knowledge_base::kb_get_pages,
        // molecule
        molecule::mol_init,
        molecule::mol_add_relation,
        molecule::mol_delete_relation,
        molecule::mol_get_relation,
        molecule::mol_find_by_molecule,
        molecule::mol_find_similar,
        molecule::mol_find_same_as,
        molecule::mol_get_stats,
        molecule::mol_assign_cluster,
        molecule::mol_remove_from_cluster,
        molecule::mol_get_cluster_members,
        molecule::mol_get_molecule_clusters,
        molecule::mol_list_clusters,
        molecule::mol_find_analogs_with_activity,
        molecule::mol_scaffold_profile,
        molecule::mol_find_activity_cliffs,
        molecule::mol_dedup_batch,
        // mol_store
        mol_store::mol_store_init,
        mol_store::mol_store_add,
        mol_store::mol_store_list,
        mol_store::mol_store_get,
        mol_store::mol_store_search,
        mol_store::mol_store_delete,
        mol_store::mol_store_stats,
        mol_store::mol_store_search_by_smiles,
        mol_store::mol_store_list_by_doc,
        mol_store::mol_store_update,
        mol_store::mol_store_update_batch,
        // notes
        notes::notes_list,
        notes::notes_get,
        notes::notes_save,
        notes::notes_delete,
        notes::notes_backlinks,
        // sidecar
        sidecar::sidecar_status,
        sidecar::sidecar_restart,
        // resource_manager
        crate::core::resource_manager::resources_check,
        crate::core::resource_manager::resources_status,
        crate::core::resource_manager::resources_get_model_path,
        crate::core::resource_manager::resources_catalog,
    ]
}
