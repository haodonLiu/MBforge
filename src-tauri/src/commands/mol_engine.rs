//! Unified Tauri state for MoleculeEngine.
//!
//! Replaces the previous `MolDbState` (RwLock<Option<MoleculeRelationDb>>)
//! and `MolStoreState` (AsyncMutex<Option<MoleculeDatabase>>) with a single
//! `MoleculeEngineState` that holds one `MoleculeEngine` per project.
//!
//! Project switching: `get_or_init_engine` compares the stored project_root
//! with the requested one. On mismatch, the old engine is dropped and a
//! new one is opened. This prevents the previous silent-wrong-project bug
//! where switching projects kept the old project's DB connection.

use crate::core::molecule::molecule_engine::MoleculeEngine;
use std::path::PathBuf;
use std::sync::Arc;
use tokio::sync::Mutex as AsyncMutex;

pub struct MoleculeEngineState {
    pub inner: Arc<AsyncMutex<Option<(String, MoleculeEngine)>>>,
}

impl MoleculeEngineState {
    pub fn new() -> Self {
        Self {
            inner: Arc::new(AsyncMutex::new(None)),
        }
    }
}

/// Initialize or return the existing MoleculeEngine for a project.
///
/// If the engine was previously initialized for a different `project_root`,
/// the old engine is dropped and a new one is opened. This makes
/// `agent_switch_project` (and any caller that passes a new root) safe.
pub async fn get_or_init_engine(
    state: &MoleculeEngineState,
    project_root: &str,
) -> Result<(), String> {
    let mut guard = state.inner.lock().await;

    if let Some((ref existing_root, _)) = *guard {
        if existing_root == project_root {
            return Ok(());
        }
        log::info!(
            "MoleculeEngine switching from {} to {}",
            existing_root,
            project_root
        );
    }

    let root = PathBuf::from(project_root);
    let engine =
        MoleculeEngine::new(&root).map_err(|e| format!("MoleculeEngine init failed: {}", e))?;
    *guard = Some((project_root.to_string(), engine));
    log::info!(
        "MoleculeEngine initialized for project_root={}",
        project_root
    );
    Ok(())
}
