//! Tauri commands for molecule store operations via MoleculeEngine.
//!
//! Previously held a separate `MolStoreState`; now unified under
//! `MoleculeEngineState` alongside relation / cluster / SAR commands.
//!
//! All engine access goes through `with_engine` (see `mol_engine.rs`) to
//! eliminate the lock + map_or boilerplate that every command used to repeat.

use crate::commands::mol_engine::{get_or_init_engine, with_engine, MoleculeEngineState};
use mbforge_domain::molecule::molecule_store::MoleculeRecord;

#[tauri::command]
pub async fn mol_store_init(
    state: tauri::State<'_, MoleculeEngineState>,
    project_root: String,
) -> Result<(), String> {
    get_or_init_engine(&state, &project_root).await?;
    log::info!("mol_store_init: project_root={}", project_root);
    Ok(())
}

#[tauri::command]
pub async fn mol_store_add(
    state: tauri::State<'_, MoleculeEngineState>,
    project_root: String,
    mol_id: String,
    esmiles: String,
    name: Option<String>,
    source_doc: Option<String>,
    activity: Option<f64>,
    activity_type: Option<String>,
    units: Option<String>,
    source_type: Option<String>,
) -> Result<(), String> {
    with_engine(&state, &project_root, |engine| {
        Box::pin(async move {
            let mut record = MoleculeRecord::new(&mol_id, &esmiles);
            if let Some(n) = name {
                record.name = n;
            }
            if let Some(sd) = source_doc {
                record.source_doc = sd;
            }
            record.activity = activity;
            if let Some(at) = activity_type {
                record.activity_type = at;
            }
            if let Some(u) = units {
                record.units = u;
            }
            record.source_type = source_type.unwrap_or_else(|| "manual".to_string());
            engine.add_molecule(&record).await
        })
    })
    .await
}

#[tauri::command]
pub async fn mol_store_list(
    state: tauri::State<'_, MoleculeEngineState>,
    project_root: String,
    limit: Option<usize>,
    offset: Option<usize>,
    source_type: Option<String>,
    status: Option<String>,
) -> Result<Vec<MoleculeRecord>, String> {
    with_engine(&state, &project_root, |engine| {
        Box::pin(async move {
            engine
                .list_all(
                    limit.unwrap_or(100),
                    offset.unwrap_or(0),
                    source_type.as_deref(),
                    status.as_deref(),
                )
                .await
        })
    })
    .await
}

#[tauri::command]
pub async fn mol_store_get(
    state: tauri::State<'_, MoleculeEngineState>,
    project_root: String,
    mol_id: String,
) -> Result<Option<MoleculeRecord>, String> {
    with_engine(&state, &project_root, |engine| {
        Box::pin(async move { engine.get_molecule(&mol_id).await })
    })
    .await
}

#[tauri::command]
pub async fn mol_store_search(
    state: tauri::State<'_, MoleculeEngineState>,
    project_root: String,
    query: String,
) -> Result<Vec<MoleculeRecord>, String> {
    with_engine(&state, &project_root, |engine| {
        Box::pin(async move { engine.search_text(&query).await })
    })
    .await
}

#[tauri::command]
pub async fn mol_store_delete(
    state: tauri::State<'_, MoleculeEngineState>,
    project_root: String,
    mol_id: String,
) -> Result<bool, String> {
    with_engine(&state, &project_root, |engine| {
        Box::pin(async move { engine.delete_molecule(&mol_id).await })
    })
    .await
}

/// 鏇存柊鍒嗗瓙鐨勫叏閮ㄥ彲缂栬緫瀛楁.
///
/// 鐢ㄤ簬 OCR 鐭娴佺▼锛氱敤鎴蜂慨姝?SMILES 鍚庢壒閲忓啓鍥炴暟鎹簱.
/// 杩斿洖 true 琛ㄧず mol_id 瀛樺湪骞跺凡鏇存柊;false 琛ㄧず mol_id 涓嶅瓨鍦?
#[tauri::command]
pub async fn mol_store_update(
    state: tauri::State<'_, MoleculeEngineState>,
    project_root: String,
    record: MoleculeRecord,
) -> Result<bool, String> {
    with_engine(&state, &project_root, |engine| {
        Box::pin(async move { engine.update_molecule(&record).await })
    })
    .await
}

/// 鎵归噺鏇存柊澶氫釜鍒嗗瓙.
///
/// 涓€娆′簨鍔?閮ㄥ垎澶辫触涓嶉樆濉炲叾浠栨垚鍔熼」.
/// 杩斿洖 (updated_count, failed_mol_ids).
#[tauri::command]
pub async fn mol_store_update_batch(
    state: tauri::State<'_, MoleculeEngineState>,
    project_root: String,
    records: Vec<MoleculeRecord>,
) -> Result<serde_json::Value, String> {
    with_engine(&state, &project_root, |engine| {
        Box::pin(async move {
            let (updated, failed) = engine.update_molecules_batch(&records).await?;
            Ok(serde_json::json!({
                "updated": updated,
                "failed": failed,
            }))
        })
    })
    .await
}

#[tauri::command]
pub async fn mol_store_stats(
    state: tauri::State<'_, MoleculeEngineState>,
    project_root: String,
) -> Result<serde_json::Value, String> {
    with_engine(&state, &project_root, |engine| {
        Box::pin(async move { engine.get_store_stats().await })
    })
    .await
}

#[tauri::command]
pub async fn mol_store_search_by_smiles(
    state: tauri::State<'_, MoleculeEngineState>,
    project_root: String,
    smiles: String,
) -> Result<Option<MoleculeRecord>, String> {
    with_engine(&state, &project_root, |engine| {
        Box::pin(async move { engine.search_by_smiles(&smiles).await })
    })
    .await
}

#[tauri::command]
pub async fn mol_store_list_by_doc(
    state: tauri::State<'_, MoleculeEngineState>,
    project_root: String,
    doc_id: String,
) -> Result<Vec<MoleculeRecord>, String> {
    with_engine(&state, &project_root, |engine| {
        Box::pin(async move { engine.search_by_source(&doc_id).await })
    })
    .await
}
