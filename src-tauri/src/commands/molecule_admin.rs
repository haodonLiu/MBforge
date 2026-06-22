//! MoleculeEngine CRUD Tauri commands.
//!
//! 既有 `molecule.rs` 已暴露关系/聚类/dedup/SAR 等"业务分析"命令；
//! 本文件补全 engine 的**基础读写** surface：
//! - 读：get / search_by_smiles / search_text / list / store_stats / check_markush / parse_esmiles
//! - 写：add / update / update_status / delete / add_similarity
//!
//! 与既有 `mol_store::*` 的区别：`mol_store` 命令以"独立小参数"暴露
//! （mol_id + esmiles + name + ...），侧重"快速录入"；`mol_admin::*` 直接
//! 接收/返回完整 `MoleculeRecord` JSON，侧重"管理面板 / 调试 / 数据迁移"。

use crate::commands::mol_engine::MoleculeEngineState;
use crate::core::molecule::molecule_engine::MoleculeEngine;
use crate::core::molecule::molecule_store::MoleculeRecord;

macro_rules! engine_or_err {
    ($guard:expr) => {
        $guard
            .as_ref()
            .map(|(_, e): &(String, MoleculeEngine)| e)
            .ok_or_else(|| "MoleculeEngine not initialized".to_string())
    };
}

// ============================================================================
// 读
// ============================================================================

/// 按 mol_id 查询单条分子
#[tauri::command]
pub async fn mol_admin_get(
    state: tauri::State<'_, MoleculeEngineState>,
    project_root: String,
    mol_id: String,
) -> Result<Option<MoleculeRecord>, String> {
    crate::commands::mol_engine::get_or_init_engine(&state, &project_root).await?;
    let guard = state.inner.lock().await;
    engine_or_err!(guard)?
        .get_molecule(&mol_id)
        .await
        .map_err(|e| e.to_string())
}

/// 按 SMILES 精确查询
#[tauri::command]
pub async fn mol_admin_search_by_smiles(
    state: tauri::State<'_, MoleculeEngineState>,
    project_root: String,
    smiles: String,
) -> Result<Option<MoleculeRecord>, String> {
    crate::commands::mol_engine::get_or_init_engine(&state, &project_root).await?;
    let guard = state.inner.lock().await;
    engine_or_err!(guard)?
        .search_by_smiles(&smiles)
        .await
        .map_err(|e| e.to_string())
}

/// FTS 全文搜索（name / notes / source_doc）
#[tauri::command]
pub async fn mol_admin_search_text(
    state: tauri::State<'_, MoleculeEngineState>,
    project_root: String,
    query: String,
) -> Result<Vec<MoleculeRecord>, String> {
    crate::commands::mol_engine::get_or_init_engine(&state, &project_root).await?;
    let guard = state.inner.lock().await;
    engine_or_err!(guard)?
        .search_text(&query)
        .await
        .map_err(|e| e.to_string())
}

/// 分页列举（可选 source_type / status 过滤）
#[tauri::command]
pub async fn mol_admin_list(
    state: tauri::State<'_, MoleculeEngineState>,
    project_root: String,
    limit: usize,
    offset: usize,
    source_type: Option<String>,
    status: Option<String>,
) -> Result<Vec<MoleculeRecord>, String> {
    crate::commands::mol_engine::get_or_init_engine(&state, &project_root).await?;
    let guard = state.inner.lock().await;
    engine_or_err!(guard)?
        .list_all(limit, offset, source_type.as_deref(), status.as_deref())
        .await
        .map_err(|e| e.to_string())
}

/// 库统计（total / by_status / by_source_type / fts_index_size）
#[tauri::command]
pub async fn mol_admin_store_stats(
    state: tauri::State<'_, MoleculeEngineState>,
    project_root: String,
) -> Result<serde_json::Value, String> {
    crate::commands::mol_engine::get_or_init_engine(&state, &project_root).await?;
    let guard = state.inner.lock().await;
    engine_or_err!(guard)?
        .get_store_stats()
        .await
        .map_err(|e| e.to_string())
}

/// Markush 覆盖度检查（engine wrapper；与 chem_markush_check 路径不同，走 engine store）
#[tauri::command]
pub async fn mol_admin_check_markush(
    state: tauri::State<'_, MoleculeEngineState>,
    project_root: String,
    esmiles: String,
    query: String,
    ctx: Option<String>,
) -> Result<crate::core::chem::markush::MarkushOverlap, String> {
    crate::commands::mol_engine::get_or_init_engine(&state, &project_root).await?;
    let guard = state.inner.lock().await;
    Ok(engine_or_err!(guard)?.check_markush(&esmiles, &query, ctx.as_deref()))
}

/// E-SMILES → MarkushPattern（engine wrapper）
#[tauri::command]
pub async fn mol_admin_parse_esmiles(
    state: tauri::State<'_, MoleculeEngineState>,
    project_root: String,
    input: String,
) -> Result<crate::core::chem::markush::MarkushPattern, String> {
    crate::commands::mol_engine::get_or_init_engine(&state, &project_root).await?;
    let guard = state.inner.lock().await;
    Ok(engine_or_err!(guard)?.parse_esmiles(&input))
}

// ============================================================================
// 写
// ============================================================================

/// 插入单条分子
#[tauri::command]
pub async fn mol_admin_add(
    state: tauri::State<'_, MoleculeEngineState>,
    project_root: String,
    record: MoleculeRecord,
) -> Result<(), String> {
    crate::commands::mol_engine::get_or_init_engine(&state, &project_root).await?;
    let guard = state.inner.lock().await;
    engine_or_err!(guard)?
        .add_molecule(&record)
        .await
        .map_err(|e| e.to_string())
}

/// 更新整条分子
#[tauri::command]
pub async fn mol_admin_update(
    state: tauri::State<'_, MoleculeEngineState>,
    project_root: String,
    record: MoleculeRecord,
) -> Result<bool, String> {
    crate::commands::mol_engine::get_or_init_engine(&state, &project_root).await?;
    let guard = state.inner.lock().await;
    engine_or_err!(guard)?
        .update_molecule(&record)
        .await
        .map_err(|e| e.to_string())
}

/// 仅更新 status 字段
#[tauri::command]
pub async fn mol_admin_update_status(
    state: tauri::State<'_, MoleculeEngineState>,
    project_root: String,
    mol_id: String,
    status: String,
) -> Result<bool, String> {
    crate::commands::mol_engine::get_or_init_engine(&state, &project_root).await?;
    let guard = state.inner.lock().await;
    engine_or_err!(guard)?
        .update_status(&mol_id, &status)
        .await
        .map_err(|e| e.to_string())
}

/// 物理删除单条分子
#[tauri::command]
pub async fn mol_admin_delete(
    state: tauri::State<'_, MoleculeEngineState>,
    project_root: String,
    mol_id: String,
) -> Result<bool, String> {
    crate::commands::mol_engine::get_or_init_engine(&state, &project_root).await?;
    let guard = state.inner.lock().await;
    engine_or_err!(guard)?
        .delete_molecule(&mol_id)
        .await
        .map_err(|e| e.to_string())
}

/// 添加相似度关系（mol_a <-> mol_b, score）
#[tauri::command]
pub async fn mol_admin_add_similarity(
    state: tauri::State<'_, MoleculeEngineState>,
    project_root: String,
    mol_a_id: String,
    mol_b_id: String,
    score: f64,
) -> Result<i64, String> {
    crate::commands::mol_engine::get_or_init_engine(&state, &project_root).await?;
    let guard = state.inner.lock().await;
    engine_or_err!(guard)?
        .add_similarity_relation(&mol_a_id, &mol_b_id, score)
        .await
        .map_err(|e| e.to_string())
}
