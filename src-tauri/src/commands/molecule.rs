use std::sync::Arc;
use tokio::sync::RwLock;

use crate::core::molecule_cluster::{self, ClusterInfo};
use crate::core::molecule_db::{MoleculeRelation, MoleculeRelationDb, RelationStats, RelationType};
use crate::core::molecule_dedup::{self, DedupResult};
use crate::core::sar_query::{ActivityCliff, AnalogWithActivity, ScaffoldProfile};

macro_rules! log_err {
    ($fmt:literal, $($arg:expr),+) => {{
        let msg = format!($fmt, $($arg),+);
        log::error!("{}", msg);
        msg
    }};
    ($msg:expr) => {{
        let msg: &str = $msg;
        log::error!("{}", msg);
        msg.to_string()
    }};
}

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

fn _db<'a>(guard: &'a Option<MoleculeRelationDb>) -> Result<&'a MoleculeRelationDb, String> {
    guard.as_ref().ok_or_else(|| log_err!("MoleculeDB not initialized"))
}

#[tauri::command]
pub async fn mol_init(
    state: tauri::State<'_, MolDbState>,
    project_root: String,
) -> Result<(), String> {
    let root = std::path::Path::new(&project_root);
    log::info!("mol_init: project_root={}", project_root);
    let db = MoleculeRelationDb::new(root).map_err(|e| {
        log::error!("mol_init failed for {}: {}", project_root, e);
        e.to_string()
    })?;
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
    let db = _db(&guard)?;
    let rel_type = RelationType::from_str(&relation_type)
        .ok_or_else(|| log_err!("Invalid relation type: {}", relation_type))?;
    let rel = MoleculeRelation {
        id: None,
        mol_a_id,
        mol_b_id,
        relation_type: rel_type,
        score,
        metadata,
        created_at: crate::core::helpers::now_rfc3339(),
    };
    db.add_relation(&rel).map_err(|e| {
        log::error!("mol_add_relation failed: {}", e);
        e.to_string()
    })
}

#[tauri::command]
pub async fn mol_delete_relation(
    state: tauri::State<'_, MolDbState>,
    id: i64,
) -> Result<bool, String> {
    let guard = state.inner.read().await;
    let db = _db(&guard)?;
    db.delete_relation(id).map_err(|e| {
        log::error!("mol_delete_relation id={} failed: {}", id, e);
        e.to_string()
    })
}

#[tauri::command]
pub async fn mol_get_relation(
    state: tauri::State<'_, MolDbState>,
    id: i64,
) -> Result<Option<MoleculeRelation>, String> {
    let guard = state.inner.read().await;
    let db = _db(&guard)?;
    db.get_relation(id).map_err(|e| {
        log::error!("mol_get_relation id={} failed: {}", id, e);
        e.to_string()
    })
}

#[tauri::command]
pub async fn mol_find_by_molecule(
    state: tauri::State<'_, MolDbState>,
    mol_id: String,
) -> Result<Vec<MoleculeRelation>, String> {
    let guard = state.inner.read().await;
    let db = _db(&guard)?;
    db.find_by_molecule(&mol_id).map_err(|e| {
        log::error!("mol_find_by_molecule mol_id={} failed: {}", mol_id, e);
        e.to_string()
    })
}

#[tauri::command]
pub async fn mol_find_similar(
    state: tauri::State<'_, MolDbState>,
    mol_id: String,
    min_score: f64,
) -> Result<Vec<(MoleculeRelation, f64)>, String> {
    let guard = state.inner.read().await;
    let db = _db(&guard)?;
    db.find_similar(&mol_id, min_score).map_err(|e| {
        log::error!("mol_find_similar mol_id={} failed: {}", mol_id, e);
        e.to_string()
    })
}

#[tauri::command]
pub async fn mol_find_same_as(
    state: tauri::State<'_, MolDbState>,
    mol_id: String,
) -> Result<Vec<MoleculeRelation>, String> {
    let guard = state.inner.read().await;
    let db = _db(&guard)?;
    db.find_same_as(&mol_id).map_err(|e| {
        log::error!("mol_find_same_as mol_id={} failed: {}", mol_id, e);
        e.to_string()
    })
}

#[tauri::command]
pub async fn mol_get_stats(
    state: tauri::State<'_, MolDbState>,
) -> Result<RelationStats, String> {
    let guard = state.inner.read().await;
    let db = _db(&guard)?;
    db.get_stats().map_err(|e| {
        log::error!("mol_get_stats failed: {}", e);
        e.to_string()
    })
}

#[tauri::command]
pub async fn mol_assign_cluster(
    state: tauri::State<'_, MolDbState>,
    mol_id: String,
    cluster_id: String,
) -> Result<i64, String> {
    let guard = state.inner.read().await;
    let db = _db(&guard)?;
    molecule_cluster::assign_to_cluster(&mol_id, &cluster_id, db).map_err(|e| {
        log::error!("mol_assign_cluster mol_id={} cluster_id={} failed: {}", mol_id, cluster_id, e);
        e.to_string()
    })
}

#[tauri::command]
pub async fn mol_remove_from_cluster(
    state: tauri::State<'_, MolDbState>,
    mol_id: String,
    cluster_id: String,
) -> Result<bool, String> {
    let guard = state.inner.read().await;
    let db = _db(&guard)?;
    molecule_cluster::remove_from_cluster(&mol_id, &cluster_id, db).map_err(|e| {
        log::error!("mol_remove_from_cluster mol_id={} cluster_id={} failed: {}", mol_id, cluster_id, e);
        e.to_string()
    })
}

#[tauri::command]
pub async fn mol_get_cluster_members(
    state: tauri::State<'_, MolDbState>,
    cluster_id: String,
) -> Result<ClusterInfo, String> {
    let guard = state.inner.read().await;
    let db = _db(&guard)?;
    molecule_cluster::get_cluster_members(&cluster_id, db).map_err(|e| {
        log::error!("mol_get_cluster_members cluster_id={} failed: {}", cluster_id, e);
        e.to_string()
    })
}

#[tauri::command]
pub async fn mol_get_molecule_clusters(
    state: tauri::State<'_, MolDbState>,
    mol_id: String,
) -> Result<Vec<String>, String> {
    let guard = state.inner.read().await;
    let db = _db(&guard)?;
    molecule_cluster::get_molecule_clusters(&mol_id, db).map_err(|e| {
        log::error!("mol_get_molecule_clusters mol_id={} failed: {}", mol_id, e);
        e.to_string()
    })
}

#[tauri::command]
pub async fn mol_list_clusters(
    state: tauri::State<'_, MolDbState>,
) -> Result<Vec<ClusterInfo>, String> {
    let guard = state.inner.read().await;
    let db = _db(&guard)?;
    molecule_cluster::list_clusters(db).map_err(|e| {
        log::error!("mol_list_clusters failed: {}", e);
        e.to_string()
    })
}

#[tauri::command]
pub async fn mol_find_analogs_with_activity(
    state: tauri::State<'_, MolDbState>,
    mol_id: String,
    min_similarity: f64,
) -> Result<Vec<AnalogWithActivity>, String> {
    let guard = state.inner.read().await;
    let db = _db(&guard)?;
    let mconn = db.molecules_conn().map_err(|e| {
        log::error!("mol_find_analogs_with_activity db conn failed: {}", e);
        e.to_string()
    })?;
    crate::core::sar_query::find_analogs_with_activity(&mol_id, min_similarity, db, &mconn).map_err(|e| {
        log::error!("mol_find_analogs_with_activity mol_id={} failed: {}", mol_id, e);
        e.to_string()
    })
}

#[tauri::command]
pub async fn mol_scaffold_profile(
    state: tauri::State<'_, MolDbState>,
    scaffold_esmiles: String,
) -> Result<ScaffoldProfile, String> {
    let guard = state.inner.read().await;
    let db = _db(&guard)?;
    let mconn = db.molecules_conn().map_err(|e| {
        log::error!("mol_scaffold_profile db conn failed: {}", e);
        e.to_string()
    })?;
    crate::core::sar_query::scaffold_activity_profile(&scaffold_esmiles, &mconn).map_err(|e| {
        log::error!("mol_scaffold_profile esmiles={} failed: {}", scaffold_esmiles, e);
        e.to_string()
    })
}

#[tauri::command]
pub async fn mol_find_activity_cliffs(
    state: tauri::State<'_, MolDbState>,
    min_similarity: f64,
    min_activity_ratio: f64,
) -> Result<Vec<ActivityCliff>, String> {
    let guard = state.inner.read().await;
    let db = _db(&guard)?;
    let mconn = db.molecules_conn().map_err(|e| {
        log::error!("mol_find_activity_cliffs db conn failed: {}", e);
        e.to_string()
    })?;
    crate::core::sar_query::find_activity_cliffs(min_similarity, min_activity_ratio, &mconn).map_err(|e| {
        log::error!("mol_find_activity_cliffs failed: sim={} ratio={} err={}", min_similarity, min_activity_ratio, e);
        e.to_string()
    })
}

#[tauri::command]
pub async fn mol_dedup_batch(
    state: tauri::State<'_, MolDbState>,
    new_mols: Vec<(String, String)>,
    same_as_threshold: f64,
) -> Result<DedupResult, String> {
    let guard = state.inner.read().await;
    let db = _db(&guard)?;
    let sidecar_url = crate::core::constants::sidecar_url();
    log::info!("mol_dedup_batch: {} molecules, threshold={}", new_mols.len(), same_as_threshold);
    Ok(molecule_dedup::run_dedup_batch(
        &new_mols,
        db,
        &sidecar_url,
        same_as_threshold,
    ))
}


