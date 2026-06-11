use crate::commands::mol_engine::{get_or_init_engine, MoleculeEngineState};
use crate::core::molecule::molecule_db::{MoleculeRelation, RelationType};
use crate::core::molecule::molecule_engine::{
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
        .map(|(_, e)| e)
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
        .map(|(_, e)| e)
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
        .map(|(_, e)| e)
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
        .map(|(_, e)| e)
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
        .map(|(_, e)| e)
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
        .map(|(_, e)| e)
        .ok_or_else(|| log_err!("MoleculeEngine not initialized"))?;
    engine.find_same_as(&mol_id).map_err(|e| {
        log::error!("mol_find_same_as mol_id={} failed: {}", mol_id, e);
        e.to_string()
    })
}

#[tauri::command]
pub async fn mol_get_stats(
    state: tauri::State<'_, MoleculeEngineState>,
) -> Result<crate::core::molecule::molecule_db::RelationStats, String> {
    let guard = state.inner.lock().await;
    let engine = guard
        .as_ref()
        .map(|(_, e)| e)
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
        .map(|(_, e)| e)
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
        .map(|(_, e)| e)
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
        .map(|(_, e)| e)
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
        .map(|(_, e)| e)
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
        .map(|(_, e)| e)
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
        .map(|(_, e)| e)
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
    project_root: String,
    scaffold_esmiles: String,
) -> Result<ScaffoldProfile, String> {
    get_or_init_engine(&state, &project_root).await?;
    let guard = state.inner.lock().await;
    let engine = guard
        .as_ref()
        .map(|(_, e)| e)
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
    project_root: String,
    min_similarity: f64,
    min_activity_ratio: f64,
) -> Result<Vec<ActivityCliff>, String> {
    get_or_init_engine(&state, &project_root).await?;
    let guard = state.inner.lock().await;
    let engine = guard
        .as_ref()
        .map(|(_, e)| e)
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
        .map(|(_, e)| e)
        .ok_or_else(|| log_err!("MoleculeEngine not initialized"))?;
    log::info!(
        "mol_dedup_batch: {} molecules, threshold={}",
        new_mols.len(),
        same_as_threshold
    );
    Ok(engine.dedup_batch(&new_mols, same_as_threshold))
}

/// 子结构搜索：Tanimoto 预过滤 + VF2 精确验证（纯 Rust）
///
/// 三级漏斗：
/// 1. 加载所有分子的 SMILES
/// 2. Tanimoto 预过滤（>0.3）快速排除不相关分子
/// 3. VF2 子结构精确验证
#[tauri::command]
pub async fn mol_search_substructure(
    state: tauri::State<'_, MoleculeEngineState>,
    query_smiles: String,
    tanimoto_threshold: Option<f64>,
) -> Result<Vec<serde_json::Value>, String> {
    let guard = state.inner.lock().await;
    let engine = guard
        .as_ref()
        .map(|(_, e)| e)
        .ok_or_else(|| log_err!("MoleculeEngine not initialized"))?;

    let db = engine.store();
    let threshold = tanimoto_threshold.unwrap_or(0.3);

    // 1. 加载所有分子
    let all_mols = db.get_all_smiles().map_err(|e| format!("get_all_smiles: {}", e))?;
    if all_mols.is_empty() {
        return Ok(vec![]);
    }

    // 2. 纯 Rust Tanimoto 预过滤 + VF2 子结构搜索
    let candidates: Vec<(String, String)> = all_mols.iter().map(|(id, s)| (id.clone(), s.clone())).collect();
    let matches = crate::core::chem::chem::substructure_search_with_filter(
        &query_smiles,
        &candidates,
        threshold,
    ).map_err(|e| format!("Substructure search failed: {}", e))?;

    // 构建返回结果
    let results: Vec<serde_json::Value> = matches
        .iter()
        .map(|(mol_id, smiles, _score)| {
            serde_json::json!({
                "mol_id": mol_id,
                "esmiles": smiles,
            })
        })
        .collect();

    log::info!(
        "Substructure search: {} final matches for '{}'",
        results.len(),
        query_smiles
    );

    Ok(results)
}

// ============================================================================
// 纯 Rust chematic 化学信息学（无 Python sidecar 依赖）
// ============================================================================

/// 校验 SMILES — 调用本地 chematic，纯 Rust。
///
/// 前端可代替 Python 端 `validate_smiles`，避免启动 model_server。
#[tauri::command]
pub async fn chem_validate_smiles(smiles: String) -> crate::core::chem::chem::SmilesValidation {
    crate::core::chem::chem::validate_smiles(&smiles)
}

/// 计算两个 SMILES 之间的 Tanimoto 相似度（ECFP4）。
#[tauri::command]
pub async fn chem_tanimoto_similarity(
    smiles_a: String,
    smiles_b: String,
) -> Result<f64, String> {
    crate::core::chem::chem::tanimoto_similarity(&smiles_a, &smiles_b)
}

/// GESim 相似度：基于图熵的分子相似度（Shiokawa et al. 2025）。
/// 与 `chem_tanimoto_similarity` 互补：Tanimoto 用 ECFP4 指纹
/// 算 Jaccard，GESim 用 von Neumann 图熵算 QJS。
///
/// - `smiles_a` / `smiles_b`: 双方 SMILES
/// - `use_scaler`: 是否套 `logistic_scaler`（让相似度分布更平滑）
#[tauri::command]
pub async fn gesim_similarity(
    smiles_a: String,
    smiles_b: String,
    use_scaler: Option<bool>,
) -> Result<f64, String> {
    use crate::core::chem::gesim;
    use chematic_smiles::parse;

    let mol_a = parse(&smiles_a).map_err(|e| format!("SMILES a parse error: {e}"))?;
    let mol_b = parse(&smiles_b).map_err(|e| format!("SMILES b parse error: {e}"))?;

    let raw = gesim::similarity_raw(&mol_a, &mol_b);
    Ok(if use_scaler.unwrap_or(false) {
        // Defaults: l=1.0, k=12.0, x0=0.5（标准 logistic 形状，居中 0.5）
        gesim::logistic_scaler(raw, 1.0, 12.0, 0.5)
    } else {
        raw
    })
}

/// 批量 Tanimoto 预过滤。
///
/// # Arguments
/// - `query_smiles`: 查询 SMILES
/// - `candidates`: `[(mol_id, smiles), ...]`
/// - `threshold`: Tanimoto 阈值（默认 0.5）
///
/// # Returns
/// 超过阈值的 `[(mol_id, smiles, score), ...]`，按 score 降序
#[tauri::command]
pub async fn chem_tanimoto_batch_filter(
    query_smiles: String,
    candidates: Vec<(String, String)>,
    threshold: Option<f64>,
) -> Result<Vec<(String, String, f64)>, String> {
    crate::core::chem::chem::tanimoto_batch_filter(&query_smiles, &candidates, threshold.unwrap_or(0.5))
}
