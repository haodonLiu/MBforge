//! Tauri commands for molecule store operations via MoleculeEngine.
//!
//! Previously held a separate `MolStoreState`; now unified under
//! `MoleculeEngineState` alongside relation / cluster / SAR commands.

use crate::commands::mol_engine::{get_or_init_engine, MoleculeEngineState};
use crate::core::molecule_store::MoleculeRecord;

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
    get_or_init_engine(&state, &project_root).await?;
    let guard = state.inner.lock().await;
    let engine = guard.as_ref().ok_or("MoleculeEngine not initialized")?;

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

    engine.add_molecule(&record).map_err(|e| e.to_string())
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
    get_or_init_engine(&state, &project_root).await?;
    let guard = state.inner.lock().await;
    let engine = guard.as_ref().ok_or("MoleculeEngine not initialized")?;

    engine.list_all(
        limit.unwrap_or(100),
        offset.unwrap_or(0),
        source_type.as_deref(),
        status.as_deref(),
    ).map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn mol_store_get(
    state: tauri::State<'_, MoleculeEngineState>,
    project_root: String,
    mol_id: String,
) -> Result<Option<MoleculeRecord>, String> {
    get_or_init_engine(&state, &project_root).await?;
    let guard = state.inner.lock().await;
    let engine = guard.as_ref().ok_or("MoleculeEngine not initialized")?;
    engine.get_molecule(&mol_id).map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn mol_store_search(
    state: tauri::State<'_, MoleculeEngineState>,
    project_root: String,
    query: String,
) -> Result<Vec<MoleculeRecord>, String> {
    get_or_init_engine(&state, &project_root).await?;
    let guard = state.inner.lock().await;
    let engine = guard.as_ref().ok_or("MoleculeEngine not initialized")?;
    engine.search_text(&query).map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn mol_store_delete(
    state: tauri::State<'_, MoleculeEngineState>,
    project_root: String,
    mol_id: String,
) -> Result<bool, String> {
    get_or_init_engine(&state, &project_root).await?;
    let guard = state.inner.lock().await;
    let engine = guard.as_ref().ok_or("MoleculeEngine not initialized")?;
    engine.delete_molecule(&mol_id).map_err(|e| e.to_string())
}

/// 更新分子的全部可编辑字段.
///
/// 用于 OCR 矫正流程：用户修正 SMILES 后批量写回数据库.
/// 返回 true 表示 mol_id 存在并已更新;false 表示 mol_id 不存在.
#[tauri::command]
pub async fn mol_store_update(
    state: tauri::State<'_, MoleculeEngineState>,
    project_root: String,
    record: MoleculeRecord,
) -> Result<bool, String> {
    get_or_init_engine(&state, &project_root).await?;
    let guard = state.inner.lock().await;
    let engine = guard.as_ref().ok_or("MoleculeEngine not initialized")?;
    engine.update_molecule(&record)
}

/// 批量更新多个分子.
///
/// 一次事务,部分失败不阻塞其他成功项.
/// 返回 (updated_count, failed_mol_ids).
#[tauri::command]
pub async fn mol_store_update_batch(
    state: tauri::State<'_, MoleculeEngineState>,
    project_root: String,
    records: Vec<MoleculeRecord>,
) -> Result<serde_json::Value, String> {
    get_or_init_engine(&state, &project_root).await?;
    let guard = state.inner.lock().await;
    let engine = guard.as_ref().ok_or("MoleculeEngine not initialized")?;
    let (updated, failed) = engine.update_molecules_batch(&records)?;
    Ok(serde_json::json!({
        "updated": updated,
        "failed": failed,
    }))
}

#[tauri::command]
pub async fn mol_store_stats(
    state: tauri::State<'_, MoleculeEngineState>,
    project_root: String,
) -> Result<serde_json::Value, String> {
    get_or_init_engine(&state, &project_root).await?;
    let guard = state.inner.lock().await;
    let engine = guard.as_ref().ok_or("MoleculeEngine not initialized")?;
    engine.get_store_stats().map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn mol_store_search_by_smiles(
    state: tauri::State<'_, MoleculeEngineState>,
    project_root: String,
    smiles: String,
) -> Result<Option<MoleculeRecord>, String> {
    get_or_init_engine(&state, &project_root).await?;
    let guard = state.inner.lock().await;
    let engine = guard.as_ref().ok_or("MoleculeEngine not initialized")?;
    engine.search_by_smiles(&smiles).map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn mol_store_list_by_doc(
    state: tauri::State<'_, MoleculeEngineState>,
    project_root: String,
    doc_id: String,
) -> Result<Vec<MoleculeRecord>, String> {
    get_or_init_engine(&state, &project_root).await?;
    let guard = state.inner.lock().await;
    let engine = guard.as_ref().ok_or("MoleculeEngine not initialized")?;
    engine.search_by_source(&doc_id).map_err(|e| e.to_string())
}
