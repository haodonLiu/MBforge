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

use mbforge_domain::molecule::molecule_engine::MoleculeEngine;
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
    let engine = MoleculeEngine::new(&root)
        .await
        .map_err(|e| format!("MoleculeEngine init failed: {}", e))?;
    *guard = Some((project_root.to_string(), engine));
    log::info!(
        "MoleculeEngine initialized for project_root={}",
        project_root
    );
    Ok(())
}

/// Run an async closure with the project's `MoleculeEngine`.
///
/// Initializes the engine for `project_root` (switching projects if needed),
/// locks the state, then invokes `f` with a shared reference to the engine.
/// Centralizes the boilerplate previously duplicated in every `mol_store_*`
/// and (most) `molecule_*` Tauri commands.
///
/// `f` must return a boxed future because the engine methods are async and
/// the closure borrows the `&MoleculeEngine` (which lives only as long as
/// the state guard). Boxed futures avoid the higher-ranked lifetime
/// constraint of an unboxed `impl Future` here.
///
/// Example:
/// ```ignore
/// with_engine(&state, &root, |engine| {
///     Box::pin(async move { engine.get_molecule(&id).await })
/// })
/// .await
/// ```
pub async fn with_engine<F, T>(
    state: &MoleculeEngineState,
    project_root: &str,
    f: F,
) -> Result<T, String>
where
    F: for<'a> FnOnce(
        &'a MoleculeEngine,
    )
        -> std::pin::Pin<Box<dyn std::future::Future<Output = Result<T, String>> + Send + 'a>>,
{
    get_or_init_engine(state, project_root).await?;
    let guard = state.inner.lock().await;
    let engine = guard
        .as_ref()
        .map(|(_, e)| e)
        .ok_or_else(|| "MoleculeEngine not initialized".to_string())?;
    f(engine).await
}
