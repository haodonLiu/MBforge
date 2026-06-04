use crate::commands::mol_engine::{get_or_init_engine, MoleculeEngineState};
use crate::core::molecule_db::{MoleculeRelation, RelationType};
use crate::core::molecule_engine::{
    ActivityCliff, AnalogWithActivity, ClusterInfo, DedupResult, ScaffoldProfile,
};

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

#[tauri::command]
pub async fn mol_init(
    state: tauri::State<'_, MoleculeEngineState>,
    project_root: String,
) -> Result<(), String> {
    get_or_init_engine(&state, &project_root).await
}

#[tauri::command]
pub async fn mol_add_relation(
    state: tauri::State<'_, MoleculeEngineState>,
    mol_a_id: String,
    mol_b_id: String,
    relation_type: String,
    score: Option<f64>,
    metadata: Option<serde_json::Value>,
) -> Result<i64, String> {
    let guard = state.inner.lock().await;
    let engine = guard
        .as_ref()
        .ok_or_else(|| log_err!("MoleculeEngine not initialized"))?;

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
    engine.add_relation(&rel).map_err(|e| {
        log::error!("mol_add_relation failed: {}", e);
        e.to_string()
    })
}

#[tauri::command]
pub async fn mol_delete_relation(
    state: tauri::State<'_, MoleculeEngineState>,
    id: i64,
) -> Result<bool, String> {
    let guard = state.inner.lock().await;
    let engine = guard
        .as_ref()
        .ok_or_else(|| log_err!("MoleculeEngine not initialized"))?;
    engine.delete_relation(id).map_err(|e| {
        log::error!("mol_delete_relation id={} failed: {}", id, e);
        e.to_string()
    })
}

#[tauri::command]
pub async fn mol_get_relation(
    state: tauri::State<'_, MoleculeEngineState>,
    id: i64,
) -> Result<Option<MoleculeRelation>, String> {
    let guard = state.inner.lock().await;
    let engine = guard
        .as_ref()
        .ok_or_else(|| log_err!("MoleculeEngine not initialized"))?;
    engine.get_relation(id).map_err(|e| {
        log::error!("mol_get_relation id={} failed: {}", id, e);
        e.to_string()
    })
}

#[tauri::command]
pub async fn mol_find_by_molecule(
    state: tauri::State<'_, MoleculeEngineState>,
    mol_id: String,
) -> Result<Vec<MoleculeRelation>, String> {
    let guard = state.inner.lock().await;
    let engine = guard
        .as_ref()
        .ok_or_else(|| log_err!("MoleculeEngine not initialized"))?;
    engine.find_by_molecule(&mol_id).map_err(|e| {
        log::error!("mol_find_by_molecule mol_id={} failed: {}", mol_id, e);
        e.to_string()
    })
}

#[tauri::command]
pub async fn mol_find_similar(
    state: tauri::State<'_, MoleculeEngineState>,
    mol_id: String,
    min_score: f64,
) -> Result<Vec<(MoleculeRelation, f64)>, String> {
    let guard = state.inner.lock().await;
    let engine = guard
        .as_ref()
        .ok_or_else(|| log_err!("MoleculeEngine not initialized"))?;
    engine.find_similar(&mol_id, min_score).map_err(|e| {
        log::error!("mol_find_similar mol_id={} failed: {}", mol_id, e);
        e.to_string()
    })
}

#[tauri::command]
pub async fn mol_find_same_as(
    state: tauri::State<'_, MoleculeEngineState>,
    mol_id: String,
) -> Result<Vec<MoleculeRelation>, String> {
    let guard = state.inner.lock().await;
    let engine = guard
        .as_ref()
        .ok_or_else(|| log_err!("MoleculeEngine not initialized"))?;
    engine.find_same_as(&mol_id).map_err(|e| {
        log::error!("mol_find_same_as mol_id={} failed: {}", mol_id, e);
        e.to_string()
    })
}

#[tauri::command]
pub async fn mol_get_stats(
    state: tauri::State<'_, MoleculeEngineState>,
) -> Result<crate::core::molecule_db::RelationStats, String> {
    let guard = state.inner.lock().await;
    let engine = guard
        .as_ref()
        .ok_or_else(|| log_err!("MoleculeEngine not initialized"))?;
    engine.get_relation_stats().map_err(|e| {
        log::error!("mol_get_stats failed: {}", e);
        e.to_string()
    })
}

#[tauri::command]
pub async fn mol_assign_cluster(
    state: tauri::State<'_, MoleculeEngineState>,
    mol_id: String,
    cluster_id: String,
) -> Result<i64, String> {
    let guard = state.inner.lock().await;
    let engine = guard
        .as_ref()
        .ok_or_else(|| log_err!("MoleculeEngine not initialized"))?;
    engine.assign_cluster(&mol_id, &cluster_id).map_err(|e| {
        log::error!(
            "mol_assign_cluster mol_id={} cluster_id={} failed: {}",
            mol_id,
            cluster_id,
            e
        );
        e.to_string()
    })
}

#[tauri::command]
pub async fn mol_remove_from_cluster(
    state: tauri::State<'_, MoleculeEngineState>,
    mol_id: String,
    cluster_id: String,
) -> Result<bool, String> {
    let guard = state.inner.lock().await;
    let engine = guard
        .as_ref()
        .ok_or_else(|| log_err!("MoleculeEngine not initialized"))?;
    engine
        .remove_from_cluster(&mol_id, &cluster_id)
        .map_err(|e| {
            log::error!(
                "mol_remove_from_cluster mol_id={} cluster_id={} failed: {}",
                mol_id,
                cluster_id,
                e
            );
            e.to_string()
        })
}

#[tauri::command]
pub async fn mol_get_cluster_members(
    state: tauri::State<'_, MoleculeEngineState>,
    cluster_id: String,
) -> Result<ClusterInfo, String> {
    let guard = state.inner.lock().await;
    let engine = guard
        .as_ref()
        .ok_or_else(|| log_err!("MoleculeEngine not initialized"))?;
    engine.get_cluster_members(&cluster_id).map_err(|e| {
        log::error!(
            "mol_get_cluster_members cluster_id={} failed: {}",
            cluster_id,
            e
        );
        e.to_string()
    })
}

#[tauri::command]
pub async fn mol_get_molecule_clusters(
    state: tauri::State<'_, MoleculeEngineState>,
    mol_id: String,
) -> Result<Vec<String>, String> {
    let guard = state.inner.lock().await;
    let engine = guard
        .as_ref()
        .ok_or_else(|| log_err!("MoleculeEngine not initialized"))?;
    engine.get_molecule_clusters(&mol_id).map_err(|e| {
        log::error!("mol_get_molecule_clusters mol_id={} failed: {}", mol_id, e);
        e.to_string()
    })
}

#[tauri::command]
pub async fn mol_list_clusters(
    state: tauri::State<'_, MoleculeEngineState>,
) -> Result<Vec<ClusterInfo>, String> {
    let guard = state.inner.lock().await;
    let engine = guard
        .as_ref()
        .ok_or_else(|| log_err!("MoleculeEngine not initialized"))?;
    engine.list_clusters().map_err(|e| {
        log::error!("mol_list_clusters failed: {}", e);
        e.to_string()
    })
}

#[tauri::command]
pub async fn mol_find_analogs_with_activity(
    state: tauri::State<'_, MoleculeEngineState>,
    mol_id: String,
    min_similarity: f64,
) -> Result<Vec<AnalogWithActivity>, String> {
    let guard = state.inner.lock().await;
    let engine = guard
        .as_ref()
        .ok_or_else(|| log_err!("MoleculeEngine not initialized"))?;
    engine.find_analogs(&mol_id, min_similarity).map_err(|e| {
        log::error!(
            "mol_find_analogs_with_activity mol_id={} failed: {}",
            mol_id,
            e
        );
        e.to_string()
    })
}

#[tauri::command]
pub async fn mol_scaffold_profile(
    state: tauri::State<'_, MoleculeEngineState>,
    scaffold_esmiles: String,
) -> Result<ScaffoldProfile, String> {
    let guard = state.inner.lock().await;
    let engine = guard
        .as_ref()
        .ok_or_else(|| log_err!("MoleculeEngine not initialized"))?;
    engine.scaffold_profile(&scaffold_esmiles).map_err(|e| {
        log::error!(
            "mol_scaffold_profile esmiles={} failed: {}",
            scaffold_esmiles,
            e
        );
        e.to_string()
    })
}

#[tauri::command]
pub async fn mol_find_activity_cliffs(
    state: tauri::State<'_, MoleculeEngineState>,
    min_similarity: f64,
    min_activity_ratio: f64,
) -> Result<Vec<ActivityCliff>, String> {
    let guard = state.inner.lock().await;
    let engine = guard
        .as_ref()
        .ok_or_else(|| log_err!("MoleculeEngine not initialized"))?;
    engine
        .find_activity_cliffs(min_similarity, min_activity_ratio)
        .map_err(|e| {
            log::error!(
                "mol_find_activity_cliffs failed: sim={} ratio={} err={}",
                min_similarity,
                min_activity_ratio,
                e
            );
            e.to_string()
        })
}

#[tauri::command]
pub async fn mol_dedup_batch(
    state: tauri::State<'_, MoleculeEngineState>,
    new_mols: Vec<(String, String)>,
    same_as_threshold: f64,
) -> Result<DedupResult, String> {
    let guard = state.inner.lock().await;
    let engine = guard
        .as_ref()
        .ok_or_else(|| log_err!("MoleculeEngine not initialized"))?;
    log::info!(
        "mol_dedup_batch: {} molecules, threshold={}",
        new_mols.len(),
        same_as_threshold
    );
    Ok(engine.dedup_batch(&new_mols, same_as_threshold))
}

/// 子结构搜索：Tanimoto 预过滤 + RDKit 精确验证
///
/// 三级漏斗：
/// 1. 加载所有分子的指纹（BLOB）
/// 2. Tanimoto 预过滤（>0.3）快速排除不相关分子
/// 3. RDKit HasSubstructMatch 精确验证
#[tauri::command]
pub async fn mol_search_substructure(
    state: tauri::State<'_, MoleculeEngineState>,
    query_smiles: String,
    tanimoto_threshold: Option<f64>,
) -> Result<Vec<serde_json::Value>, String> {
    let guard = state.inner.lock().await;
    let engine = guard
        .as_ref()
        .ok_or_else(|| log_err!("MoleculeEngine not initialized"))?;

    let db = engine.store();
    let threshold = tanimoto_threshold.unwrap_or(0.3);

    // 1. 加载所有分子的指纹
    let all_mols = db.get_all_smiles().map_err(|e| format!("get_all_smiles: {}", e))?;
    if all_mols.is_empty() {
        return Ok(vec![]);
    }

    // 2. 调用 Python sidecar 计算查询分子指纹 + 批量 Tanimoto 预过滤
    let sidecar_url = crate::core::constants::sidecar_url();
    let client = reqwest::Client::new();

    // 先计算查询分子指纹
    let fp_resp = client
        .post(format!("{}/api/v1/chem/fingerprint", sidecar_url))
        .json(&serde_json::json!({"esmiles": query_smiles}))
        .send()
        .await
        .map_err(|e| format!("Fingerprint request failed: {}", e))?;

    let fp_json: serde_json::Value = fp_resp
        .json()
        .await
        .map_err(|e| format!("Fingerprint parse failed: {}", e))?;

    if !fp_json.get("success").and_then(|v| v.as_bool()).unwrap_or(false) {
        return Err(format!(
            "Fingerprint failed: {}",
            fp_json.get("error").and_then(|v| v.as_str()).unwrap_or("unknown")
        ));
    }

    // 批量 Tanimoto 预过滤
    let candidate_esmiles: Vec<String> = all_mols.iter().map(|(_, s)| s.clone()).collect();
    let tanimoto_resp = client
        .post(format!("{}/api/v1/chem/tanimoto/batch", sidecar_url))
        .json(&serde_json::json!({
            "target_esmiles": query_smiles,
            "esmiles_list": candidate_esmiles,
            "threshold": threshold,
        }))
        .send()
        .await
        .map_err(|e| format!("Tanimoto batch request failed: {}", e))?;

    let tanimoto_json: serde_json::Value = tanimoto_resp
        .json()
        .await
        .map_err(|e| format!("Tanimoto parse failed: {}", e))?;

    let filtered: Vec<String> = tanimoto_json
        .get("results")
        .and_then(|v| v.as_array())
        .map(|arr| {
            arr.iter()
                .filter_map(|r| r.get("esmiles").and_then(|v| v.as_str()).map(String::from))
                .collect()
        })
        .unwrap_or_default();

    if filtered.is_empty() {
        return Ok(vec![]);
    }

    log::info!(
        "Substructure search: {} total → {} after Tanimoto (>{})",
        all_mols.len(),
        filtered.len(),
        threshold
    );

    // 3. RDKit 子结构精确验证
    let sub_resp = client
        .post(format!("{}/api/v1/chem/substructure_search", sidecar_url))
        .json(&serde_json::json!({
            "query_smiles": query_smiles,
            "candidate_esmiles": filtered,
        }))
        .send()
        .await
        .map_err(|e| format!("Substructure search request failed: {}", e))?;

    let sub_json: serde_json::Value = sub_resp
        .json()
        .await
        .map_err(|e| format!("Substructure search parse failed: {}", e))?;

    let matches: Vec<String> = sub_json
        .get("matches")
        .and_then(|v| v.as_array())
        .map(|arr| {
            arr.iter()
                .filter_map(|v| v.as_str().map(String::from))
                .collect()
        })
        .unwrap_or_default();

    // 构建返回结果（包含分子详情）
    let mol_map: std::collections::HashMap<String, String> = all_mols.into_iter().collect();
    let results: Vec<serde_json::Value> = matches
        .iter()
        .filter_map(|esmiles| {
            let mol_id = mol_map.get(esmiles)?;
            Some(serde_json::json!({
                "mol_id": mol_id,
                "esmiles": esmiles,
            }))
        })
        .collect();

    log::info!(
        "Substructure search: {} final matches for '{}'",
        results.len(),
        query_smiles
    );

    Ok(results)
}
