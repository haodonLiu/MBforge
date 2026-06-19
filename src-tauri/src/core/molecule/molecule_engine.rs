#![allow(dead_code)]
//! Unified molecule analysis engine.
//!
//! Holds both `MoleculeDatabase` (store / FTS5) and `MoleculeRelationDb`
//! (relations / clusters) behind a single facade.  All molecule-related
//! Tauri commands and Agent tools go through this struct instead of
//! opening independent DB connections.

use std::path::Path;
use tokio::sync::Mutex;

use crate::core::chem::markush;
use crate::core::molecule::molecule_db::{MoleculeRelation, MoleculeRelationDb, RelationStats};
use crate::core::molecule::molecule_store::{MoleculeDatabase, MoleculeRecord};

// Re-export types that callers need.
pub use crate::core::chem::markush::{MarkushOverlap, MarkushPattern};
pub use crate::core::chem::sar_query::{
    ActivityCliff, ActivitySummary, AnalogWithActivity, ScaffoldActivityRecord, ScaffoldProfile,
};
pub use crate::core::molecule::molecule_cluster::ClusterInfo;
pub use crate::core::molecule::molecule_dedup::DedupResult;

// ---------------------------------------------------------------------------
// MoleculeEngine
// ---------------------------------------------------------------------------

pub struct MoleculeEngine {
    store: Mutex<MoleculeDatabase>,
    relation_db: MoleculeRelationDb,
}

impl MoleculeEngine {
    /// Open (or create) both the molecule store and relation DB for a project.
    ///
    /// Both connections point to `{project_root}/.mbforge/molecules.db`.
    /// WAL mode is enabled by the underlying modules, so concurrent reads
    /// across the two connections are safe.
    pub async fn new(project_root: &Path) -> Result<Self, String> {
        let store = Mutex::new(
            MoleculeDatabase::open(project_root)
                .map_err(|e| format!("Failed to open molecule store: {}", e))?,
        );
        let relation_db = MoleculeRelationDb::new(project_root)
            .await
            .map_err(|e| format!("Failed to open relation DB: {}", e))?;
        Ok(Self { store, relation_db })
    }

    // =====================================================================
    // Store operations (delegated to molecule_store.rs)
    // =====================================================================

    pub fn add_molecule(&self, record: &MoleculeRecord) -> Result<(), String> {
        self.store.blocking_lock().add_molecule(record)
    }

    pub fn add_molecules_batch(&self, records: &[MoleculeRecord]) -> Result<usize, String> {
        self.store.blocking_lock().add_molecules_batch(records)
    }

    /// 获取底层 MoleculeDatabase 锁 guard
    pub fn store(&self) -> tokio::sync::MutexGuard<'_, MoleculeDatabase> {
        self.store.blocking_lock()
    }

    pub fn get_molecule(&self, mol_id: &str) -> Result<Option<MoleculeRecord>, String> {
        self.store.blocking_lock().get_molecule(mol_id)
    }

    pub fn search_by_smiles(&self, smiles: &str) -> Result<Option<MoleculeRecord>, String> {
        self.store.blocking_lock().search_by_smiles(smiles)
    }

    pub fn search_by_source(&self, doc_id: &str) -> Result<Vec<MoleculeRecord>, String> {
        self.store.blocking_lock().search_by_source(doc_id)
    }

    pub fn search_text(&self, query: &str) -> Result<Vec<MoleculeRecord>, String> {
        self.store.blocking_lock().search_text(query)
    }

    pub fn list_all(
        &self,
        limit: usize,
        offset: usize,
        source_type: Option<&str>,
        status: Option<&str>,
    ) -> Result<Vec<MoleculeRecord>, String> {
        self.store.blocking_lock().list_all(limit, offset, source_type, status)
    }

    pub fn delete_molecule(&self, mol_id: &str) -> Result<bool, String> {
        self.store.blocking_lock().delete_molecule(mol_id)
    }

    pub fn get_store_stats(&self) -> Result<serde_json::Value, String> {
        self.store.blocking_lock().get_stats()
    }

    pub fn update_status(&self, mol_id: &str, status: &str) -> Result<bool, String> {
        self.store.blocking_lock().update_status(mol_id, status)
    }

    pub fn update_molecule(&self, record: &MoleculeRecord) -> Result<bool, String> {
        self.store.blocking_lock().update_molecule(record)
    }

    pub fn update_molecules_batch(
        &self,
        records: &[MoleculeRecord],
    ) -> Result<(usize, Vec<String>), String> {
        self.store.blocking_lock().update_molecules_batch(records)
    }
    // =====================================================================
    // Relation operations (delegated to molecule_db.rs)
    // =====================================================================

    pub async fn add_relation(&self, rel: &MoleculeRelation) -> Result<i64, String> {
        self.relation_db.add_relation(rel).await
    }

    pub async fn delete_relation(&self, id: i64) -> Result<bool, String> {
        self.relation_db.delete_relation(id).await
    }

    pub async fn get_relation(&self, id: i64) -> Result<Option<MoleculeRelation>, String> {
        self.relation_db.get_relation(id).await
    }

    pub async fn find_by_molecule(&self, mol_id: &str) -> Result<Vec<MoleculeRelation>, String> {
        self.relation_db.find_by_molecule(mol_id).await
    }

    pub async fn find_similar(
        &self,
        mol_id: &str,
        min_score: f64,
    ) -> Result<Vec<(MoleculeRelation, f64)>, String> {
        self.relation_db.find_similar(mol_id, min_score).await
    }

    pub async fn find_same_as(&self, mol_id: &str) -> Result<Vec<MoleculeRelation>, String> {
        self.relation_db.find_same_as(mol_id).await
    }

    pub async fn get_relation_stats(&self) -> Result<RelationStats, String> {
        self.relation_db.get_stats().await
    }

    // =====================================================================
    // Cluster operations (delegated to molecule_cluster.rs)
    // =====================================================================

    pub async fn assign_cluster(&self, mol_id: &str, cluster_id: &str) -> Result<i64, String> {
        crate::core::molecule::molecule_cluster::assign_to_cluster(
            mol_id,
            cluster_id,
            &self.relation_db,
        )
        .await
    }

    pub async fn remove_from_cluster(
        &self,
        mol_id: &str,
        cluster_id: &str,
    ) -> Result<bool, String> {
        crate::core::molecule::molecule_cluster::remove_from_cluster(
            mol_id,
            cluster_id,
            &self.relation_db,
        )
        .await
    }

    pub async fn get_cluster_members(&self, cluster_id: &str) -> Result<ClusterInfo, String> {
        crate::core::molecule::molecule_cluster::get_cluster_members(cluster_id, &self.relation_db)
            .await
    }

    pub async fn get_molecule_clusters(&self, mol_id: &str) -> Result<Vec<String>, String> {
        crate::core::molecule::molecule_cluster::get_molecule_clusters(mol_id, &self.relation_db)
            .await
    }

    pub async fn list_clusters(&self) -> Result<Vec<ClusterInfo>, String> {
        crate::core::molecule::molecule_cluster::list_clusters(&self.relation_db).await
    }

    // =====================================================================
    // SAR operations (delegated to sar_query.rs)
    // =====================================================================

    pub async fn find_analogs(
        &self,
        mol_id: &str,
        min_sim: f64,
    ) -> Result<Vec<AnalogWithActivity>, String> {
        // 先异步查询相似关系，避免在 await 期间持有 store 的同步锁。
        let analogs = self
            .relation_db
            .find_similar(mol_id, min_sim)
            .await
            .map_err(|e| format!("find_similar failed: {}", e))?;

        let store = self.store.lock().await;
        let mconn = store.conn();

        let mut results = Vec::new();
        for (rel, score) in analogs {
            let neighbor_id = if rel.mol_a_id == mol_id {
                rel.mol_b_id.clone()
            } else {
                rel.mol_a_id.clone()
            };

            if let Some(record) =
                crate::core::chem::sar_query::get_molecule_activity(&neighbor_id, mconn)
            {
                results.push(AnalogWithActivity {
                    mol_id: neighbor_id,
                    esmiles: record.esmiles,
                    name: record.name,
                    similarity_score: score,
                    activity: record.activity,
                    activity_type: record.activity_type,
                    units: record.units,
                });
            }
        }

        results.sort_by(|a, b| {
            b.similarity_score
                .partial_cmp(&a.similarity_score)
                .unwrap_or(std::cmp::Ordering::Equal)
        });
        Ok(results)
    }

    pub fn scaffold_profile(&self, scaffold: &str) -> Result<ScaffoldProfile, String> {
        let store = self.store.blocking_lock();
        crate::core::chem::sar_query::scaffold_activity_profile(scaffold, store.conn())
    }

    pub fn find_activity_cliffs(
        &self,
        min_sim: f64,
        min_ratio: f64,
    ) -> Result<Vec<ActivityCliff>, String> {
        let store = self.store.blocking_lock();
        crate::core::chem::sar_query::find_activity_cliffs(min_sim, min_ratio, store.conn())
    }

    // =====================================================================
    // Dedup operations (delegated to molecule_dedup.rs)
    // =====================================================================

    pub async fn dedup_batch(&self, new_mols: &[(String, String)], threshold: f64) -> DedupResult {
        let sidecar_url = crate::core::constants::sidecar_url();
        crate::core::molecule::molecule_dedup::run_dedup_batch(
            new_mols,
            &self.relation_db,
            &sidecar_url,
            threshold,
        )
        .await
    }

    pub async fn add_similarity_relation(
        &self,
        mol_a_id: &str,
        mol_b_id: &str,
        score: f64,
    ) -> Result<i64, String> {
        crate::core::molecule::molecule_dedup::add_similarity_relation(
            mol_a_id,
            mol_b_id,
            score,
            &self.relation_db,
        )
        .await
    }

    // =====================================================================
    // Markush operations (delegated to markush.rs — pure computation)
    // =====================================================================

    pub fn check_markush(&self, esmiles: &str, query: &str, ctx: Option<&str>) -> MarkushOverlap {
        markush::analyze_markush_coverage(esmiles, query, ctx)
    }

    pub fn parse_esmiles(&self, input: &str) -> MarkushPattern {
        markush::parse_esmiles(input)
    }

    // =====================================================================
    // Unified Agent tool entry
    // =====================================================================

    /// Dispatch molecule analysis actions for the Agent executor.
    ///
    /// Supported actions:
    /// - `"list"`          → params: `{ limit?: number }`
    /// - `"search_by_smiles"` → params: `{ smiles: string }`
    /// - `"search_text"`   → params: `{ query: string }`
    /// - `"get_stats"`     → params: `{}`
    /// - `"get_relation_stats"` → params: `{}`
    /// - `"scaffold_profile"` → params: `{ scaffold: string }`
    /// - `"find_analogs"`  → params: `{ mol_id: string, min_similarity?: number }`
    /// - `"find_activity_cliffs"` → params: `{ min_similarity?: number, min_activity_ratio?: number }`
    /// - `"check_markush"` → params: `{ esmiles: string, query_smiles: string, rgroup_text?: string }`
    /// - `"list_clusters"` → params: `{}`
    /// - `"dedup_batch"`   → params: `{ mols: [[id, smiles], ...], threshold?: number }`
    pub async fn analyze(
        &self,
        action: &str,
        params: serde_json::Value,
    ) -> Result<serde_json::Value, String> {
        match action {
            "list" => {
                let limit = params["limit"].as_u64().unwrap_or(20) as usize;
                let mols = self.list_all(limit, 0, None, None)?;
                Ok(serde_json::to_value(&mols).map_err(|e| e.to_string())?)
            }
            "search_by_smiles" => {
                let smiles = params["smiles"].as_str().unwrap_or("");
                let mut results = Vec::new();
                if let Ok(Some(rec)) = self.search_by_smiles(smiles) {
                    results.push(rec);
                }
                if let Ok(recs) = self.search_text(smiles) {
                    for r in recs {
                        if !results
                            .iter()
                            .any(|x: &MoleculeRecord| x.mol_id == r.mol_id)
                        {
                            results.push(r);
                        }
                    }
                }
                Ok(serde_json::to_value(&results).map_err(|e| e.to_string())?)
            }
            "search_text" => {
                let query = params["query"].as_str().unwrap_or("");
                let mols = self.search_text(query)?;
                Ok(serde_json::to_value(&mols).map_err(|e| e.to_string())?)
            }
            "get_stats" => {
                let stats = self.get_store_stats()?;
                Ok(stats)
            }
            "get_relation_stats" => {
                let stats = self.get_relation_stats().await?;
                Ok(serde_json::to_value(&stats).map_err(|e| e.to_string())?)
            }
            "scaffold_profile" => {
                let scaffold = params["scaffold"].as_str().unwrap_or("");
                let profile = self.scaffold_profile(scaffold)?;
                Ok(serde_json::to_value(&profile).map_err(|e| e.to_string())?)
            }
            "find_analogs" => {
                let mol_id = params["mol_id"].as_str().unwrap_or("");
                let min_sim = params["min_similarity"].as_f64().unwrap_or(0.7);
                let analogs = self.find_analogs(mol_id, min_sim).await?;
                Ok(serde_json::to_value(&analogs).map_err(|e| e.to_string())?)
            }
            "find_activity_cliffs" => {
                let min_sim = params["min_similarity"].as_f64().unwrap_or(0.7);
                let min_ratio = params["min_activity_ratio"].as_f64().unwrap_or(10.0);
                let cliffs = self.find_activity_cliffs(min_sim, min_ratio)?;
                Ok(serde_json::to_value(&cliffs).map_err(|e| e.to_string())?)
            }
            "check_markush" => {
                let esmiles = params["esmiles"].as_str().unwrap_or("");
                let query = params["query_smiles"].as_str().unwrap_or("");
                let ctx = params["rgroup_text"].as_str();
                let result = self.check_markush(esmiles, query, ctx);
                Ok(serde_json::to_value(&result).map_err(|e| e.to_string())?)
            }
            "list_clusters" => {
                let clusters = self.list_clusters().await?;
                Ok(serde_json::to_value(&clusters).map_err(|e| e.to_string())?)
            }
            "dedup_batch" => {
                let mols: Vec<(String, String)> = serde_json::from_value(params["mols"].clone())
                    .map_err(|e| format!("Invalid mols param: {}", e))?;
                let threshold = params["threshold"].as_f64().unwrap_or(1.0);
                let result = self.dedup_batch(&mols, threshold).await;
                Ok(serde_json::to_value(&result).map_err(|e| e.to_string())?)
            }
            _ => Err(format!("Unknown molecule action: {}", action)),
        }
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use crate::core::molecule::molecule_db::RelationType;
    use std::path::PathBuf;

    fn temp_project() -> (tempfile::TempDir, PathBuf) {
        let tmp = tempfile::TempDir::new().unwrap();
        let root = tmp.path().to_path_buf();
        std::fs::create_dir_all(root.join(".mbforge")).unwrap();
        (tmp, root)
    }

    #[tokio::test]
    async fn test_engine_opens_both_schemas() {
        let (_tmp, root) = temp_project();
        let engine = MoleculeEngine::new(&root).await.unwrap();

        // Store schema should exist
        let stats = engine.get_store_stats().unwrap();
        assert_eq!(stats["total"], 0);

        // Relation schema should exist
        let rel_stats = engine.get_relation_stats().await.unwrap();
        assert_eq!(rel_stats.total, 0);
    }

    #[tokio::test]
    async fn test_analyze_list_empty() {
        let (_tmp, root) = temp_project();
        let engine = MoleculeEngine::new(&root).await.unwrap();

        let result = engine
            .analyze("list", serde_json::json!({"limit": 10}))
            .await
            .unwrap();
        let mols: Vec<MoleculeRecord> = serde_json::from_value(result).unwrap();
        assert!(mols.is_empty());
    }

    #[tokio::test]
    async fn test_analyze_unknown_action() {
        let (_tmp, root) = temp_project();
        let engine = MoleculeEngine::new(&root).await.unwrap();

        let err = engine
            .analyze("unknown_action", serde_json::json!({}))
            .await
            .unwrap_err();
        assert!(err.contains("Unknown molecule action"));
    }

    #[tokio::test]
    async fn test_roundtrip_store_and_relation() {
        let (_tmp, root) = temp_project();
        let engine = MoleculeEngine::new(&root).await.unwrap();

        // Add a molecule via store
        let mut rec = MoleculeRecord::new("m1", "CCO");
        rec.name = "Ethanol".to_string();
        engine.add_molecule(&rec).unwrap();

        // Add a relation via relation DB
        let rel = MoleculeRelation {
            id: None,
            mol_a_id: "m1".to_string(),
            mol_b_id: "m2".to_string(),
            relation_type: RelationType::Similar,
            score: Some(0.95),
            metadata: None,
            created_at: crate::core::helpers::now_rfc3339(),
        };
        let rid = engine.add_relation(&rel).await.unwrap();
        assert!(rid > 0);

        // Verify store can read it back
        let loaded = engine.get_molecule("m1").unwrap().unwrap();
        assert_eq!(loaded.name, "Ethanol");

        // Verify relation DB can read it back
        let found = engine.find_by_molecule("m1").await.unwrap();
        assert_eq!(found.len(), 1);
    }
}
