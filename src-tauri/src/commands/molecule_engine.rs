//! Unified Tauri state for MoleculeEngine.
//!
//! Replaces the previous `MolDbState` (RwLock<Option<MoleculeRelationDb>>)
//! and `MolStoreState` (AsyncMutex<Option<MoleculeDatabase>>) with a single
//! `MoleculeEngineState` that holds one `MoleculeEngine` per project.

use crate::core::molecule::molecule_engine::MoleculeEngine;
use std::path::PathBuf;
use std::sync::Arc;
use tokio::sync::Mutex as AsyncMutex;

pub struct MoleculeEngineState {
    pub inner: Arc<AsyncMutex<Option<MoleculeEngine>>>,
}

impl MoleculeEngineState {
    pub fn new() -> Self {
        Self {
            inner: Arc::new(AsyncMutex::new(None)),
        }
    }
}

/// Initialize or return the existing MoleculeEngine for a project.
pub async fn get_or_init_engine(
    state: &MoleculeEngineState,
    project_root: &str,
) -> Result<(), String> {
    let mut guard = state.inner.lock().await;

    // If already initialized for the same root, return OK.
    // We don't re-open for a different root here; the caller is responsible
    // for project switching via a re-init command.
    if guard.is_some() {
        return Ok(());
    }

    let root = PathBuf::from(project_root);
    let engine =
        MoleculeEngine::new(&root).map_err(|e| format!("MoleculeEngine init failed: {}", e))?;
    *guard = Some(engine);
    log::info!(
        "MoleculeEngine initialized for project_root={}",
        project_root
    );
    Ok(())
}
