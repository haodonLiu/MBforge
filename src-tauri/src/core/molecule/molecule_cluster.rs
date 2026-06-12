use serde::{Deserialize, Serialize};

use super::molecule_db::{MoleculeRelation, MoleculeRelationDb, RelationType};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ClusterInfo {
    pub cluster_id: String,
    pub member_count: usize,
    pub members: Vec<String>,
    pub metadata: serde_json::Value,
}

pub async fn assign_to_cluster(
    mol_id: &str,
    cluster_id: &str,
    db: &MoleculeRelationDb,
) -> Result<i64, String> {
    let rel = MoleculeRelation {
        id: None,
        mol_a_id: mol_id.to_string(),
        mol_b_id: cluster_id.to_string(),
        relation_type: RelationType::Cluster,
        score: None,
        metadata: Some(serde_json::json!({
            "cluster_id": cluster_id,
        })),
        created_at: super::super::helpers::now_rfc3339(),
    };
    db.add_relation(&rel).await
}

pub async fn remove_from_cluster(
    mol_id: &str,
    cluster_id: &str,
    db: &MoleculeRelationDb,
) -> Result<bool, String> {
    let conn = db.relations_conn().await;
    let affected = conn
        .execute(
            "DELETE FROM molecule_relations
             WHERE relation_type = 'cluster'
               AND mol_a_id = ?1
               AND mol_b_id = ?2",
            rusqlite::params![mol_id, cluster_id],
        )
        .map_err(|e| format!("Failed to remove from cluster: {}", e))?;
    Ok(affected > 0)
}

pub async fn get_cluster_members(
    cluster_id: &str,
    db: &MoleculeRelationDb,
) -> Result<ClusterInfo, String> {
    let conn = db.relations_conn().await;
    let mut stmt = conn
        .prepare(
            "SELECT mol_a_id, metadata FROM molecule_relations
             WHERE relation_type = 'cluster'
               AND mol_b_id = ?1",
        )
        .map_err(|e| format!("Prepare failed: {}", e))?;
    let mut rows = stmt
        .query(rusqlite::params![cluster_id])
        .map_err(|e| format!("Query failed: {}", e))?;

    let mut members: Vec<String> = Vec::new();
    let mut metadata_map: std::collections::HashMap<String, serde_json::Value> =
        std::collections::HashMap::new();

    while let Some(row) = rows
        .next()
        .map_err(|e| format!("Row fetch failed: {}", e))?
    {
        let mol_id: String = row.get(0).unwrap_or_default();
        let meta_str: Option<String> = row.get(1).ok();
        if let Some(m) = meta_str.and_then(|s| serde_json::from_str::<serde_json::Value>(&s).ok()) {
            metadata_map.insert(mol_id.clone(), m);
        }
        members.push(mol_id);
    }

    let all_metadata = serde_json::json!({
        "cluster_id": cluster_id,
        "member_count": members.len(),
    });

    Ok(ClusterInfo {
        cluster_id: cluster_id.to_string(),
        member_count: members.len(),
        members,
        metadata: all_metadata,
    })
}

pub async fn get_molecule_clusters(mol_id: &str, db: &MoleculeRelationDb) -> Result<Vec<String>, String> {
    let conn = db.relations_conn().await;
    let mut stmt = conn
        .prepare(
            "SELECT mol_b_id FROM molecule_relations
             WHERE relation_type = 'cluster'
               AND mol_a_id = ?1",
        )
        .map_err(|e| format!("Prepare failed: {}", e))?;
    let mut rows = stmt
        .query(rusqlite::params![mol_id])
        .map_err(|e| format!("Query failed: {}", e))?;

    let mut clusters: Vec<String> = Vec::new();
    while let Some(row) = rows
        .next()
        .map_err(|e| format!("Row fetch failed: {}", e))?
    {
        let cluster_id: String = row.get(0).unwrap_or_default();
        clusters.push(cluster_id);
    }
    Ok(clusters)
}

pub async fn list_clusters(db: &MoleculeRelationDb) -> Result<Vec<ClusterInfo>, String> {
    // 使用独立同步连接收集 cluster id；通过块作用域确保 statement/connection
    // 在后续 await 之前被释放，避免非 Send 的 rusqlite 对象跨越 await 点。
    let cluster_ids: Vec<String> = {
        let conn = db
            .molecules_conn()
            .map_err(|e| format!("Failed to open molecules conn: {}", e))?;
        let mut stmt = conn
            .prepare(
                "SELECT DISTINCT mol_b_id FROM molecule_relations
                 WHERE relation_type = 'cluster'",
            )
            .map_err(|e| format!("Prepare failed: {}", e))?;
        let mut rows = stmt.query([]).map_err(|e| format!("Query failed: {}", e))?;

        let mut ids: Vec<String> = Vec::new();
        while let Some(row) = rows
            .next()
            .map_err(|e| format!("Row fetch failed: {}", e))?
        {
            let cid: String = row.get(0).unwrap_or_default();
            ids.push(cid);
        }
        ids
    };

    let mut infos: Vec<ClusterInfo> = Vec::new();
    for cid in cluster_ids {
        if let Ok(info) = get_cluster_members(&cid, db).await {
            infos.push(info);
        }
    }
    Ok(infos)
}
