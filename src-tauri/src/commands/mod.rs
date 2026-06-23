pub mod agent;
pub mod chem_ops;
pub mod classifier;
pub mod detection_cache;
pub mod extractor;
pub mod file_ops;
pub mod llm;
pub mod mol_engine;
pub mod mol_store;
pub mod molecode;
pub mod molecule;
pub mod molecule_admin;
pub mod notes;
pub mod pdf;
pub mod pipeline;
pub mod project_ops;
pub mod result_pane;
pub mod settings;
pub mod settings_extra;
pub mod sidecar;
pub mod text_ops;

/// 返回 Tauri invoke handler，聚合所有命令模块的 IPC 函数。
///
/// 新增命令时，只需在对应模块中定义 `#[tauri::command]` 函数，
/// 然后在此列表的对应分组中追加一行即可；`main.rs` 无需修改。
pub fn handler() -> impl Fn(tauri::ipc::Invoke<tauri::Wry>) -> bool + Send + Sync + 'static {
    tauri::generate_handler![
        // file_ops
        file_ops::read_text_file,
        file_ops::upload_files,
        file_ops::delete_file,
        file_ops::open_file,
        file_ops::open_external_url,
        // project_ops
        project_ops::open_project,
        project_ops::scan_project_files,
        project_ops::list_project_documents,
        project_ops::list_project_documents_with_status,
        project_ops::get_document_output_status,
        project_ops::get_file_tree,
        project_ops::enqueue_unresolved_documents,
        // pdf
        pdf::classify_pdf,
        pdf::inspect_pdf,
        pdf::confirm_ocr,
        pdf::extract_text,
        pdf::get_document_ocr_layout,
        pdf::augment_markdown_with_images,
        // ingest queue
        pdf::ingest_enqueue,
        pdf::ingest_list,
        pdf::ingest_stats,
        pdf::ingest_cancel,
        pdf::ingest_retry,
        pdf::ingest_set_priority,
        pdf::ingest_cancel_all_pending,
        pdf::ingest_cleanup,
        pdf::ingest_delete_task,
        pdf::ingest_mark_done,
        pdf::ingest_mark_failed,
        pdf::ingest_dequeue,
        // text_ops
        text_ops::text_chunk,
        // detection_cache
        detection_cache::cached_extract_page,
        detection_cache::get_cached_page_detections,
        detection_cache::get_detection_cache_stats,
        detection_cache::clear_detection_cache,
        detection_cache::clear_detection_cache_doc,
        detection_cache::vlm_chem_coref,
        detection_cache::label_for_mol_bbox,
        detection_cache::batch_quick_moldet_scan,
        // classifier
        classifier::classify_page,
        classifier::classify_document,
        // extractor
        extractor::extract_esmiles_candidates,
        extractor::extract_activities,
        extractor::extract_associated_molecules,
        extractor::extract_with_associations,
        // agent
        agent::agent_init,
        agent::agent_create_session,
        agent::agent_chat,
        agent::agent_chat_stream,
        agent::agent_switch_project,
        agent::agent_clear,
        agent::agent_destroy_session,
        agent::audit_log_get,
        agent::agent_get_history,
        // parsers
        pipeline::process_document,
        pipeline::index_project,
        // knowledge_base
        crate::core::document::knowledge_base::kb_search,
        crate::core::document::knowledge_base::kb_search_stream,
        crate::core::document::knowledge_base::kb_get_structure,
        crate::core::document::knowledge_base::kb_get_pages,
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
        molecule::mol_search_substructure,
        molecule::chem_validate_smiles,
        molecule::chem_tanimoto_similarity,
        molecule::chem_tanimoto_batch_filter,
        molecule::gesim_similarity,
        // molecode
        molecode::esmiles_to_molecode_cmd,
        molecode::chem_descriptors_cmd,
        // chem_ops (pure chem computation, no state)
        chem_ops::chem_canonicalize,
        chem_ops::chem_substructure_search,
        chem_ops::chem_smiles_to_molecode,
        chem_ops::chem_smiles_to_esmiles,
        chem_ops::chem_parse_esmiles_tags,
        chem_ops::chem_sanitize_esmiles,
        chem_ops::chem_separate_esmiles_layers,
        chem_ops::chem_validate_smiles_batch,
        chem_ops::chem_preprocess_smiles,
        chem_ops::chem_preprocess_rgroup_name,
        chem_ops::chem_markush_parse,
        chem_ops::chem_markush_check,
        chem_ops::chem_core_smiles,
        chem_ops::chem_gesim_atom_mapping,
        // molecule_admin (engine CRUD)
        molecule_admin::mol_admin_get,
        molecule_admin::mol_admin_search_by_smiles,
        molecule_admin::mol_admin_search_text,
        molecule_admin::mol_admin_list,
        molecule_admin::mol_admin_store_stats,
        molecule_admin::mol_admin_check_markush,
        molecule_admin::mol_admin_parse_esmiles,
        molecule_admin::mol_admin_add,
        molecule_admin::mol_admin_update,
        molecule_admin::mol_admin_update_status,
        molecule_admin::mol_admin_delete,
        molecule_admin::mol_admin_add_similarity,
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
        sidecar::environment_check,
        // settings
        settings::get_settings,
        settings::save_settings,
        settings::app_build_info,
        settings::export_settings,
        settings::reset_settings,
        settings::config_dir_path,
        // llm env probe
        llm::get_llm_env_config,
        llm::test_llm_connection,
        crate::core::project::resource_manager::resources_check,
        crate::core::project::resource_manager::resources_status,
        crate::core::project::resource_manager::resources_get_model_path,
        crate::core::project::resource_manager::resources_catalog,
        crate::core::project::resource_manager::models_download,
        crate::core::project::resource_manager::models_download_subfile,
        crate::core::project::resource_manager::models_cancel_download,
        crate::core::project::resource_manager::models_delete,
        crate::core::project::resource_manager::models_delete_subfile,
        crate::core::project::resource_manager::models_test,
        crate::core::project::resource_manager::models_cache_dir_info,
        crate::core::project::resource_manager::refresh_resolved_paths,
        // result_pane (PDF right-hand panel: coref chain + page parse)
        result_pane::get_molecule_coref_chain,
        result_pane::get_page_parse_result,
        // extended settings (cache + recent projects)
        settings_extra::cache_size,
        settings_extra::cache_clear,
        settings_extra::projects_list_recent,
        settings_extra::projects_add_recent,
        settings_extra::projects_remove_recent,
        settings_extra::projects_clear_recent,
        // SAR analysis
        crate::core::chem::sar::sar_find_scaffold,
        crate::core::chem::sar::sar_decompose,
        crate::core::chem::sar::sar_build_matrix,
        crate::core::chem::sar::sar_heatmap,
    ]
}
