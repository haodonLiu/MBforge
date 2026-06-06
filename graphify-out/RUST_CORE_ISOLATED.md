# Rust Core 层孤立节点完整清单

总计: 239 个节点

## src-tauri/src/core/agent/arxiv.rs

- [code] Client (degree=1)
- [code] urlencoding_encodes_space_as_plus() (degree=1)
- [code] urlencoding_handles_ascii_punctuation() (degree=1)
- [code] urlencoding_handles_cjk() (degree=1)
- [code] urlencoding_handles_emoji() (degree=1)
- [code] urlencoding_handles_empty_string() (degree=1)
- [code] urlencoding_handles_mixed_cjk_and_ascii() (degree=1)
- [code] urlencoding_passes_through_unreserved() (degree=1)
## src-tauri/src/core/agent/arxiv_rig.rs

- [code] ToolSet (degree=1)
## src-tauri/src/core/agent/context.rs

- [code] .set_project_context() (degree=1)
- [code] Box (degree=1)
- [code] Error (degree=1)
- [code] Result (degree=1)
## src-tauri/src/core/agent/executor_rig.rs

- [code] Default (degree=1)
- [code] GetProjectInfoArgs (degree=1)
- [code] ToolSet (degree=1)
- [code] Value (degree=1)
## src-tauri/src/core/agent/kb.rs

- [code] Option (degree=1)
- [code] PageContent (degree=1)
- [code] TreeNode (degree=1)
- [code] Value (degree=1)
## src-tauri/src/core/agent/memory.rs

- [code] .count() (degree=1)
- [code] .record_turn() (degree=1)
- [code] .reset_turn_counter() (degree=1)
- [code] Message (degree=1)
- [code] Self (degree=1)
- [code] default_confidence() (degree=1)
## src-tauri/src/core/agent/mod.rs

- [code] mod.rs (degree=0)
## src-tauri/src/core/agent/molecule.rs

- [code] String (degree=1)
- [code] Value (degree=1)
- [code] molecule.rs (degree=1)
## src-tauri/src/core/agent/observability.rs

- [code] .elapsed_ms() (degree=1)
- [code] .total_tokens() (degree=1)
- [code] Arc (degree=1)
- [code] Default (degree=1)
- [code] File (degree=1)
- [code] Mutex (degree=1)
- [code] PathBuf (degree=1)
## src-tauri/src/core/agent/rig_adapter.rs

- [code] AuditLogHook (degree=1)
- [code] CompletionResponse (degree=1)
- [code] F (degree=1)
- [code] M (degree=1)
- [code] MultiTurnStreamItem (degree=1)
- [code] PromptHook (degree=1)
- [code] R (degree=1)
- [code] Response (degree=1)
- [code] StreamingError (degree=1)
- [code] TrajectoryHook (degree=1)
- [code] test_mbforge_provider_kind_as_str() (degree=1)
## src-tauri/src/core/agent/rig_hooks.rs

- [code] CompletionResponse (degree=1)
- [code] InvalidToolCallContext (degree=1)
- [code] InvalidToolCallHookAction (degree=1)
- [code] Response (degree=1)
- [code] StreamingResponse (degree=1)
- [code] ToolCallHookAction (degree=1)
- [code] Usage (degree=1)
## src-tauri/src/core/agent/rig_memory.rs

- [code] Option (degree=1)
- [code] Sync (degree=1)
## src-tauri/src/core/agent/skills.rs

- [code] .auto_create_from_conversation() (degree=1)
- [code] .delete() (degree=1)
- [code] Box (degree=1)
- [code] Error (degree=1)
- [code] Option (degree=1)
- [code] Result (degree=1)
- [code] Self (degree=1)
## src-tauri/src/core/agent/trajectory.rs

- [code] PathBuf (degree=1)
- [code] Self (degree=1)
## src-tauri/src/core/chem/abbreviation_map.rs

- [code] String (degree=1)
- [code] Vec (degree=1)
- [code] is_non_expandable() (degree=1)
- [code] test_is_non_expandable() (degree=1)
- [code] test_normalize_bracket_digits() (degree=1)
- [code] test_normalize_caret() (degree=1)
- [code] test_normalize_case() (degree=1)
- [code] test_normalize_synonym() (degree=1)
- [code] test_normalize_trailing_punct() (degree=1)
## src-tauri/src/core/chem/chem.rs

- [code] EsTag (degree=1)
- [code] Option (degree=1)
- [code] tanimoto_bytes() (degree=1)
- [code] test_tanimoto_bytes() (degree=1)
## src-tauri/src/core/chem/esmiles.rs

- [code] test_count_wildcard_atoms() (degree=1)
## src-tauri/src/core/chem/gesim.rs

- [code] .set() (degree=1)
- [code] Option (degree=1)
- [code] String (degree=1)
## src-tauri/src/core/chem/markush.rs

- [code] AbstractRing (degree=1)
- [code] Atom (degree=1)
- [code] Bond (degree=1)
- [code] MatchLevel (degree=1)
- [code] MatchLevel (degree=1)
- [code] RGroupAttachment (degree=1)
- [code] RGroupDef (degree=1)
- [code] RGroupResult (degree=1)
- [code] Result (degree=1)
- [code] SubstituentClass (degree=1)
- [code] core_smiles() (degree=1)
- [code] is_extended() (degree=1)
- [code] test_core_smiles_extraction() (degree=1)
- [code] test_is_extended() (degree=1)
## src-tauri/src/core/chem/mod.rs

- [code] mod.rs (degree=0)
## src-tauri/src/core/chem/molecode.rs

- [code] Option (degree=1)
- [code] Self (degree=1)
- [code] test_display_label_formats() (degree=1)
- [code] test_sanitize_identifier() (degree=1)
## src-tauri/src/core/chem/sar_query.rs

- [code] ActivitySummary (degree=1)
- [code] ScaffoldActivityRecord (degree=1)
## src-tauri/src/core/config/mod.rs

- [code] mod.rs (degree=0)
## src-tauri/src/core/config/settings.rs

- [code] Box (degree=1)
- [code] Error (degree=1)
- [code] Option (degree=1)
- [code] Result (degree=1)
- [code] Vec (degree=1)
- [code] default_health_check_interval() (degree=1)
- [code] default_port() (degree=1)
- [code] default_startup_timeout() (degree=1)
- [code] default_true() (degree=1)
## src-tauri/src/core/document/content_cache.rs

- [code] ContentCacheStats (degree=1)
- [code] Option (degree=1)
- [code] Self (degree=1)
- [code] Vec (degree=1)
## src-tauri/src/core/document/document_tree.rs

- [code] Option (degree=1)
- [code] Self (degree=1)
- [code] test_parse_page_range() (degree=1)
## src-tauri/src/core/document/file_cache.rs

- [code] CacheStats (degree=1)
- [code] CacheStats (degree=1)
- [code] Option (degree=1)
- [code] Self (degree=1)
- [code] String (degree=1)
## src-tauri/src/core/document/ingest_queue.rs

- [code] .can_retry() (degree=1)
- [code] Error (degree=1)
- [code] QueueStats (degree=1)
- [code] QueueStats (degree=1)
- [code] Result (degree=1)
- [code] Row (degree=1)
- [code] TempDir (degree=1)
- [code] Vec (degree=1)
## src-tauri/src/core/document/knowledge_base.rs

- [code] AppHandle (degree=1)
- [code] EmbedConfig (degree=1)
- [code] Mutex (degree=1)
- [code] SectionChunk (degree=1)
- [code] Self (degree=1)
- [code] SemanticCache (degree=1)
- [code] SqliteVectorStore (degree=1)
- [code] StreamingResult (degree=1)
## src-tauri/src/core/document/semantic_cache.rs

- [code] .clear() (degree=1)
- [code] Connection (degree=1)
- [code] Default (degree=1)
- [code] F (degree=1)
- [code] HashMap (degree=1)
- [code] Option (degree=1)
- [code] PathBuf (degree=1)
- [code] T (degree=1)
- [code] TempDir (degree=1)
## src-tauri/src/core/document/stream_search.rs

- [code] Default (degree=1)
- [code] Option (degree=1)
- [code] String (degree=1)
## src-tauri/src/core/document/summary.rs

- [code] Option (degree=1)
- [code] String (degree=1)
## src-tauri/src/core/error.rs

- [code] Display (degree=1)
- [code] Formatter (degree=1)
- [code] From (degree=1)
- [code] Option (degree=1)
- [code] Result (degree=1)
## src-tauri/src/core/executor/arxiv.rs

- [code] Client (degree=1)
- [code] urlencoding_encodes_space_as_plus() (degree=1)
- [code] urlencoding_handles_ascii_punctuation() (degree=1)
- [code] urlencoding_handles_cjk() (degree=1)
- [code] urlencoding_handles_emoji() (degree=1)
- [code] urlencoding_handles_empty_string() (degree=1)
- [code] urlencoding_handles_mixed_cjk_and_ascii() (degree=1)
- [code] urlencoding_passes_through_unreserved() (degree=1)
## src-tauri/src/core/executor/document.rs

- [code] ToolRegistry (degree=1)
## src-tauri/src/core/executor/fs.rs

- [code] ToolRegistry (degree=1)
## src-tauri/src/core/executor/kb.rs

- [code] Option (degree=1)
- [code] PageContent (degree=1)
- [code] ToolRegistry (degree=1)
- [code] TreeNode (degree=1)
- [code] Value (degree=1)
## src-tauri/src/core/executor/literature.rs

- [code] ToolRegistry (degree=1)
- [code] literature.rs (degree=1)
## src-tauri/src/core/executor/mod.rs

- [code] Option (degree=1)
## src-tauri/src/core/executor/molecule.rs

- [code] String (degree=1)
- [code] ToolRegistry (degree=1)
- [code] Value (degree=1)
## src-tauri/src/core/helpers.rs

- [code] Box (degree=1)
- [code] Option (degree=1)
- [code] test_safe_filename() (degree=1)
- [code] test_truncate_text() (degree=1)
## src-tauri/src/core/models/catalog.rs

- [code] Default (degree=1)
- [code] Self (degree=1)
- [code] Vec (degree=1)
## src-tauri/src/core/models/download.rs

- [code] String (degree=1)
## src-tauri/src/core/models/mod.rs

- [code] mod.rs (degree=0)
## src-tauri/src/core/models/status.rs

- [code] EnvironmentReport (degree=1)
- [code] Value (degree=1)
- [code] Vec (degree=1)
## src-tauri/src/core/molecule/molecule_cluster.rs

- [code] Value (degree=1)
## src-tauri/src/core/molecule/molecule_db.rs

- [code] .as_str() (degree=1)
- [code] JsonValue (degree=1)
- [code] MutexGuard (degree=1)
- [code] Path (degree=1)
- [code] Row (degree=1)
## src-tauri/src/core/molecule/molecule_dedup.rs

- [code] Result (degree=1)
## src-tauri/src/core/molecule/molecule_engine.rs

- [code] ActivityCliff (degree=1)
- [code] AnalogWithActivity (degree=1)
- [code] DedupResult (degree=1)
- [code] MarkushOverlap (degree=1)
- [code] MarkushPattern (degree=1)
- [code] MoleculeRelationDb (degree=1)
- [code] RelationStats (degree=1)
- [code] ScaffoldProfile (degree=1)
- [code] Self (degree=1)
- [code] TempDir (degree=1)
## src-tauri/src/core/molecule/molecule_store.rs

- [code] PathBuf (degree=1)
- [code] Row (degree=1)
- [code] SqlResult (degree=1)
## src-tauri/src/core/project/mod.rs

- [code] mod.rs (degree=0)
## src-tauri/src/core/project/notes.rs

- [code] Into (degree=1)
- [code] Option (degree=1)
- [code] Self (degree=1)
## src-tauri/src/core/project/project.rs

- [code] PathBuf (degree=1)
- [code] test_detect_type() (degree=1)
## src-tauri/src/core/project/resource_manager.rs

- [code] AppHandle (degree=1)
- [code] EnvironmentReport (degree=1)
- [code] Option (degree=1)
- [code] ResourceStatusResult (degree=1)
- [code] Value (degree=1)
- [code] Vec (degree=1)
## src-tauri/src/core/types.rs

- [code] Value (degree=1)
- [code] Vec (degree=1)
## src-tauri/src/core/vector/embedding.rs

- [code] Box (degree=1)
- [code] EmbedConfig (degree=1)
- [code] Send (degree=1)
- [code] Sync (degree=1)
## src-tauri/src/core/vector/mod.rs

- [code] mod.rs (degree=0)
## src-tauri/src/core/vector/sqlite_vector_store.rs

- [code] Option (degree=1)
- [code] String (degree=1)
- [code] test_cosine_similarity() (degree=1)
## src-tauri/src/core/vector/vector_store.rs

- [code] String (degree=1)
- [code] Value (degree=1)
