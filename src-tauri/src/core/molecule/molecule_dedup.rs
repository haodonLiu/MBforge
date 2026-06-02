use serde::{Deserialize, Serialize};
use std::collections::HashSet;

use super::molecule_db::{MoleculeRelation, MoleculeRelationDb, RelationType};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DedupPair {
    pub mol_a_id: String,
    pub mol_b_id: String,
    pub confidence: f64,
    pub reason: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DedupResult {
    pub duplicates: Vec<DedupPair>,
    pub new_mols: Vec<String>,
    pub relations_added: i64,
}

pub fn canonicalize_esmiles(esmiles: &str) -> String {
    let trimmed = esmiles.trim().to_string();
    if trimmed.is_empty() {
        return String::new();
    }
    trimmed
}

pub fn run_dedup_batch(
    new_mols: &[(String, String)],
    db: &MoleculeRelationDb,
    _sidecar_url: &str,
    same_as_threshold: f64,
) -> DedupResult {
    let existing = load_existing_molecules(db);
    let mut seen_esmiles: HashSet<String> = existing
        .iter()
        .map(|(_, esmiles)| canonicalize_esmiles(esmiles))
        .collect();

    let mut duplicates = Vec::new();
    let mut new_mol_ids = Vec::new();
    let mut relations_added = 0i64;

    for (mol_id, esmiles) in new_mols {
        let normalized = canonicalize_esmiles(esmiles);
        if normalized.is_empty() {
            new_mol_ids.push(mol_id.clone());
            continue;
        }

        if let Some((match_id, _)) = existing
            .iter()
            .find(|(_, existing_esmiles)| canonicalize_esmiles(existing_esmiles).eq(&normalized))
        {
            duplicates.push(DedupPair {
                mol_a_id: mol_id.clone(),
                mol_b_id: match_id.clone(),
                confidence: 1.0,
                reason: "exact SMILES match".to_string(),
            });
        } else if seen_esmiles.contains(&normalized) {
            if let Some((match_id, _)) = new_mols
                .iter()
                .filter(|(id, _)| id.as_str() != mol_id.as_str())
                .find(|(_, s)| canonicalize_esmiles(s).eq(&normalized))
            {
                duplicates.push(DedupPair {
                    mol_a_id: mol_id.clone(),
                    mol_b_id: match_id.clone(),
                    confidence: 1.0,
                    reason: "exact SMILES match (within batch)".to_string(),
                });
            }
        } else {
            seen_esmiles.insert(normalized);
            new_mol_ids.push(mol_id.clone());
        }
    }

    for dup in &duplicates {
        if dup.confidence >= same_as_threshold {
            let rel = MoleculeRelation {
                id: None,
                mol_a_id: dup.mol_a_id.clone(),
                mol_b_id: dup.mol_b_id.clone(),
                relation_type: RelationType::SameAs,
                score: Some(dup.confidence),
                metadata: Some(serde_json::json!({
                    "reason": dup.reason,
                })),
                created_at: super::super::helpers::now_rfc3339(),
            };
            if db.add_relation(&rel).is_ok() {
                relations_added += 1;
            }
        }
    }

    DedupResult {
        duplicates,
        new_mols: new_mol_ids,
        relations_added,
    }
}

// TODO-AUDIT: silently returns empty Vec if molecules table doesn't exist.
// This causes dedup to treat all molecules as new (no duplicate detection).
// Consider logging a warning or returning an explicit error.
fn load_existing_molecules(db: &MoleculeRelationDb) -> Vec<(String, String)> {
    let conn = db.relations_conn();
    let mut stmt = match conn.prepare("SELECT mol_id, esmiles FROM molecules") {
        Ok(s) => s,
        Err(_) => return Vec::new(),
    };
    let mut result = Vec::new();
    let mut rows = match stmt.query([]) {
        Ok(r) => r,
        Err(_) => return Vec::new(),
    };
    loop {
        match rows.next() {
            Ok(Some(row)) => {
                let mol_id: String = row.get(0).unwrap_or_default();
                let esmiles: String = row.get(1).unwrap_or_default();
                result.push((mol_id, esmiles));
            }
            _ => break,
        }
    }
    result
}

pub fn add_similarity_relation(
    mol_a_id: &str,
    mol_b_id: &str,
    score: f64,
    db: &MoleculeRelationDb,
) -> Result<i64, String> {
    let rel = MoleculeRelation {
        id: None,
        mol_a_id: mol_a_id.to_string(),
        mol_b_id: mol_b_id.to_string(),
        relation_type: RelationType::Similar,
        score: Some(score),
        metadata: None,
        created_at: super::super::helpers::now_rfc3339(),
    };
    db.add_relation(&rel)
}
