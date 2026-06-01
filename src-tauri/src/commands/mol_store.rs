//! Tauri commands for MoleculeDatabase (molecule_store.rs)
//! 
//! Provides CRUD operations for molecules in the project SQLite database.

use crate::core::molecule_store::{MoleculeDatabase, MoleculeRecord};
use std::path::PathBuf;
use std::sync::Arc;
use tokio::sync::Mutex as AsyncMutex;

pub struct MolStoreState {
    pub inner: Arc<AsyncMutex<Option<MoleculeDatabase>>>,
}

impl MolStoreState {
    pub fn new() -> Self {
        Self {
            inner: Arc::new(AsyncMutex::new(None)),
        }
    }
}

async fn get_or_init_db(state: &MolStoreState, project_root: &str) -> Result<(), String> {
    let mut guard = state.inner.lock().await;
    
    if guard.is_none() {
        let root = PathBuf::from(project_root);
        let db = MoleculeDatabase::open(&root).map_err(|e| e.to_string())?;
        *guard = Some(db);
    }
    
    Ok(())
}

/// Initialize molecule store for a project
#[tauri::command]
pub async fn mol_store_init(
    state: tauri::State<'_, MolStoreState>,
    project_root: String,
) -> Result<(), String> {
    get_or_init_db(&state, &project_root).await?;
    log::info!("mol_store_init: project_root={}", project_root);
    Ok(())
}

/// Add a new molecule
#[tauri::command]
pub async fn mol_store_add(
    state: tauri::State<'_, MolStoreState>,
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
    get_or_init_db(&state, &project_root).await?;
    let guard = state.inner.lock().await;
    let db = guard.as_ref().ok_or("Database not initialized")?;

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
    // Default source_type to "manual" if not provided
    record.source_type = source_type.unwrap_or_else(|| "manual".to_string());

    db.add_molecule(&record).map_err(|e| e.to_string())
}

/// List molecules with pagination
#[tauri::command]
pub async fn mol_store_list(
    state: tauri::State<'_, MolStoreState>,
    project_root: String,
    limit: Option<usize>,
    offset: Option<usize>,
    source_type: Option<String>,
    status: Option<String>,
) -> Result<Vec<MoleculeRecord>, String> {
    get_or_init_db(&state, &project_root).await?;
    let guard = state.inner.lock().await;
    let db = guard.as_ref().ok_or("Database not initialized")?;

    db.list_all(
        limit.unwrap_or(100),
        offset.unwrap_or(0),
        source_type.as_deref(),
        status.as_deref(),
    ).map_err(|e| e.to_string())
}

/// Get a molecule by ID
#[tauri::command]
pub async fn mol_store_get(
    state: tauri::State<'_, MolStoreState>,
    project_root: String,
    mol_id: String,
) -> Result<Option<MoleculeRecord>, String> {
    get_or_init_db(&state, &project_root).await?;
    let guard = state.inner.lock().await;
    let db = guard.as_ref().ok_or("Database not initialized")?;
    db.get_molecule(&mol_id).map_err(|e| e.to_string())
}

/// Search molecules by text (FTS5)
#[tauri::command]
pub async fn mol_store_search(
    state: tauri::State<'_, MolStoreState>,
    project_root: String,
    query: String,
) -> Result<Vec<MoleculeRecord>, String> {
    get_or_init_db(&state, &project_root).await?;
    let guard = state.inner.lock().await;
    let db = guard.as_ref().ok_or("Database not initialized")?;
    db.search_text(&query).map_err(|e| e.to_string())
}

/// Delete a molecule
#[tauri::command]
pub async fn mol_store_delete(
    state: tauri::State<'_, MolStoreState>,
    project_root: String,
    mol_id: String,
) -> Result<bool, String> {
    get_or_init_db(&state, &project_root).await?;
    let guard = state.inner.lock().await;
    let db = guard.as_ref().ok_or("Database not initialized")?;
    db.delete_molecule(&mol_id).map_err(|e| e.to_string())
}

/// Get molecule statistics
#[tauri::command]
pub async fn mol_store_stats(
    state: tauri::State<'_, MolStoreState>,
    project_root: String,
) -> Result<serde_json::Value, String> {
    get_or_init_db(&state, &project_root).await?;
    let guard = state.inner.lock().await;
    let db = guard.as_ref().ok_or("Database not initialized")?;
    db.get_stats().map_err(|e| e.to_string())
}

/// Search by SMILES exact match
#[tauri::command]
pub async fn mol_store_search_by_smiles(
    state: tauri::State<'_, MolStoreState>,
    project_root: String,
    esmiles: String,
) -> Result<Option<MoleculeRecord>, String> {
    get_or_init_db(&state, &project_root).await?;
    let guard = state.inner.lock().await;
    let db = guard.as_ref().ok_or("Database not initialized")?;
    db.search_by_esmiles(&esmiles).map_err(|e| e.to_string())
}

/// List molecules by source document
#[tauri::command]
pub async fn mol_store_list_by_doc(
    state: tauri::State<'_, MolStoreState>,
    project_root: String,
    doc_id: String,
) -> Result<Vec<MoleculeRecord>, String> {
    get_or_init_db(&state, &project_root).await?;
    let guard = state.inner.lock().await;
    let db = guard.as_ref().ok_or("Database not initialized")?;
    db.search_by_source(&doc_id).map_err(|e| e.to_string())
}
