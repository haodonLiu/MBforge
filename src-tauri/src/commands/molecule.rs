use std::sync::Arc;
use tokio::sync::RwLock;

use crate::core::molecule_cluster::{self, ClusterInfo};
use crate::core::molecule_db::{MoleculeRelation, MoleculeRelationDb, RelationStats, RelationType};
use crate::core::molecule_dedup::{self, DedupResult};
use crate::core::sar_query::{ActivityCliff, AnalogWithActivity, ScaffoldProfile};

pub struct MolDbState {
    pub inner: Arc<RwLock<Option<MoleculeRelationDb>>>,
}

impl MolDbState {
    pub fn new() -> Self {
        Self {
            inner: Arc::new(RwLock::new(None)),
        }
    }
}

#[tauri::command]
pub async fn mol_init(
    state: tauri::State<'_, MolDbState>,
    project_root: String,
) -> Result<(), String> {
    let root = std::path::Path::new(&project_root);
    let db = MoleculeRelationDb::new(root)?;
    let mut guard = state.inner.write().await;
    *guard = Some(db);
    Ok(())
}

#[tauri::command]
pub async fn mol_add_relation(
    state: tauri::State<'_, MolDbState>,
    mol_a_id: String,
    mol_b_id: String,
    relation_type: String,
    score: Option<f64>,
    metadata: Option<serde_json::Value>,
) -> Result<i64, String> {
    let guard = state.inner.read().await;
    let db = guard.as_ref().ok_or("MoleculeDB not initialized")?;
    let rel_type = RelationType::from_str(&relation_type).ok_or("Invalid relation type")?;
    let rel = MoleculeRelation {
        id: None,
        mol_a_id,
        mol_b_id,
        relation_type: rel_type,
        score,
        metadata,
        created_at: chrono::Utc::now().to_rfc3339(),
    };
    db.add_relation(&rel)
}

#[tauri::command]
pub async fn mol_delete_relation(
    state: tauri::State<'_, MolDbState>,
    id: i64,
) -> Result<bool, String> {
    let guard = state.inner.read().await;
    let db = guard.as_ref().ok_or("MoleculeDB not initialized")?;
    db.delete_relation(id)
}

#[tauri::command]
pub async fn mol_get_relation(
    state: tauri::State<'_, MolDbState>,
    id: i64,
) -> Result<Option<MoleculeRelation>, String> {
    let guard = state.inner.read().await;
    let db = guard.as_ref().ok_or("MoleculeDB not initialized")?;
    db.get_relation(id)
}

#[tauri::command]
pub async fn mol_find_by_molecule(
    state: tauri::State<'_, MolDbState>,
    mol_id: String,
) -> Result<Vec<MoleculeRelation>, String> {
    let guard = state.inner.read().await;
    let db = guard.as_ref().ok_or("MoleculeDB not initialized")?;
    db.find_by_molecule(&mol_id)
}

#[tauri::command]
pub async fn mol_find_similar(
    state: tauri::State<'_, MolDbState>,
    mol_id: String,
    min_score: f64,
) -> Result<Vec<(MoleculeRelation, f64)>, String> {
    let guard = state.inner.read().await;
    let db = guard.as_ref().ok_or("MoleculeDB not initialized")?;
    db.find_similar(&mol_id, min_score)
}

#[tauri::command]
pub async fn mol_find_same_as(
    state: tauri::State<'_, MolDbState>,
    mol_id: String,
) -> Result<Vec<MoleculeRelation>, String> {
    let guard = state.inner.read().await;
    let db = guard.as_ref().ok_or("MoleculeDB not initialized")?;
    db.find_same_as(&mol_id)
}

#[tauri::command]
pub async fn mol_get_stats(
    state: tauri::State<'_, MolDbState>,
) -> Result<RelationStats, String> {
    let guard = state.inner.read().await;
    let db = guard.as_ref().ok_or("MoleculeDB not initialized")?;
    db.get_stats()
}

#[tauri::command]
pub async fn mol_assign_cluster(
    state: tauri::State<'_, MolDbState>,
    mol_id: String,
    cluster_id: String,
) -> Result<i64, String> {
    let guard = state.inner.read().await;
    let db = guard.as_ref().ok_or("MoleculeDB not initialized")?;
    molecule_cluster::assign_to_cluster(&mol_id, &cluster_id, db)
}

#[tauri::command]
pub async fn mol_remove_from_cluster(
    state: tauri::State<'_, MolDbState>,
    mol_id: String,
    cluster_id: String,
) -> Result<bool, String> {
    let guard = state.inner.read().await;
    let db = guard.as_ref().ok_or("MoleculeDB not initialized")?;
    molecule_cluster::remove_from_cluster(&mol_id, &cluster_id, db)
}

#[tauri::command]
pub async fn mol_get_cluster_members(
    state: tauri::State<'_, MolDbState>,
    cluster_id: String,
) -> Result<ClusterInfo, String> {
    let guard = state.inner.read().await;
    let db = guard.as_ref().ok_or("MoleculeDB not initialized")?;
    molecule_cluster::get_cluster_members(&cluster_id, db)
}

#[tauri::command]
pub async fn mol_get_molecule_clusters(
    state: tauri::State<'_, MolDbState>,
    mol_id: String,
) -> Result<Vec<String>, String> {
    let guard = state.inner.read().await;
    let db = guard.as_ref().ok_or("MoleculeDB not initialized")?;
    molecule_cluster::get_molecule_clusters(&mol_id, db)
}

#[tauri::command]
pub async fn mol_list_clusters(
    state: tauri::State<'_, MolDbState>,
) -> Result<Vec<ClusterInfo>, String> {
    let guard = state.inner.read().await;
    let db = guard.as_ref().ok_or("MoleculeDB not initialized")?;
    molecule_cluster::list_clusters(db)
}

#[tauri::command]
pub async fn mol_find_analogs_with_activity(
    state: tauri::State<'_, MolDbState>,
    mol_id: String,
    min_similarity: f64,
) -> Result<Vec<AnalogWithActivity>, String> {
    let guard = state.inner.read().await;
    let db = guard.as_ref().ok_or("MoleculeDB not initialized")?;
    let mconn = db.molecules_conn()?;
    crate::core::sar_query::find_analogs_with_activity(&mol_id, min_similarity, db, &mconn)
}

#[tauri::command]
pub async fn mol_scaffold_profile(
    state: tauri::State<'_, MolDbState>,
    scaffold_smiles: String,
) -> Result<ScaffoldProfile, String> {
    let guard = state.inner.read().await;
    let db = guard.as_ref().ok_or("MoleculeDB not initialized")?;
    let mconn = db.molecules_conn()?;
    crate::core::sar_query::scaffold_activity_profile(&scaffold_smiles, &mconn)
}

#[tauri::command]
pub async fn mol_find_activity_cliffs(
    state: tauri::State<'_, MolDbState>,
    min_similarity: f64,
    min_activity_ratio: f64,
) -> Result<Vec<ActivityCliff>, String> {
    let guard = state.inner.read().await;
    let db = guard.as_ref().ok_or("MoleculeDB not initialized")?;
    let mconn = db.molecules_conn()?;
    crate::core::sar_query::find_activity_cliffs(min_similarity, min_activity_ratio, &mconn)
}

#[tauri::command]
pub async fn mol_dedup_batch(
    state: tauri::State<'_, MolDbState>,
    new_mols: Vec<(String, String)>,
    same_as_threshold: f64,
) -> Result<DedupResult, String> {
    let guard = state.inner.read().await;
    let db = guard.as_ref().ok_or("MoleculeDB not initialized")?;
    let sidecar_url = std::env::var("MBFORGE_SIDECAR_URL")
        .unwrap_or_else(|_| "http://127.0.0.1:18792".to_string());
    Ok(molecule_dedup::run_dedup_batch(
        &new_mols,
        db,
        &sidecar_url,
        same_as_threshold,
    ))
}
