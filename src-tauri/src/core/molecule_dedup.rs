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

pub fn canonicalize_smiles(smiles: &str) -> String {
    let trimmed = smiles.trim().to_string();
    if trimmed.is_empty() {
        return String::new();
    }
    // TODO-AUDIT: feature "smiles-canonical" is referenced here but not defined in
    // Cargo.toml — the conditional always evaluates to false. Either add the feature
    // to [features] in Cargo.toml or remove the conditional.
    #[cfg(feature = "smiles-canonical")]
    {
        if let Ok(canon) = smiles_canonical::canonicalize(&trimmed) {
            return canon;
        }
    }
    trimmed
}

// TODO-AUDIT: call_tanimoto_sidecar is dead code — defined but never called.
// Additionally, the response field checked here is "score" but chem.py returns
// "tanimoto" — if ever wired in, this function would always fail.
pub fn call_tanimoto_sidecar(
    smiles_a: &str,
    smiles_b: &str,
    sidecar_url: &str,
) -> Result<f64, String> {
    let client = reqwest::blocking::Client::new();
    let body = serde_json::json!({
        "smiles_a": smiles_a,
        "smiles_b": smiles_b,
    });
    let resp = client
        .post(format!("{}/api/v1/chem/tanimoto", sidecar_url.trim_end_matches('/')))
        .json(&body)
        .timeout(std::time::Duration::from_secs(30))
        .send()
        .map_err(|e| format!("Tanimoto sidecar request failed: {}", e))?;
    let val: serde_json::Value = resp
        .json()
        .map_err(|e| format!("Tanimoto response parse failed: {}", e))?;
    val.get("tanimoto")
        .and_then(|v| v.as_f64())
        .ok_or_else(|| format!("Invalid tanimoto response: {}", val))
}

pub fn run_dedup_batch(
    new_mols: &[(String, String)],
    db: &MoleculeRelationDb,
    _sidecar_url: &str,
    same_as_threshold: f64,
) -> DedupResult {
    let existing = load_existing_molecules(db);
    let mut seen_smiles: HashSet<String> = existing
        .iter()
        .map(|(_, smiles)| canonicalize_smiles(smiles))
        .collect();

    let mut duplicates = Vec::new();
    let mut new_mol_ids = Vec::new();
    let mut relations_added = 0i64;

    for (mol_id, smiles) in new_mols {
        let normalized = canonicalize_smiles(smiles);
        if normalized.is_empty() {
            new_mol_ids.push(mol_id.clone());
            continue;
        }

        if let Some((match_id, _)) = existing
            .iter()
            .find(|(_, existing_smiles)| canonicalize_smiles(existing_smiles).eq(&normalized))
        {
            duplicates.push(DedupPair {
                mol_a_id: mol_id.clone(),
                mol_b_id: match_id.clone(),
                confidence: 1.0,
                reason: "exact SMILES match".to_string(),
            });
        } else if seen_smiles.contains(&normalized) {
            if let Some((match_id, _)) = new_mols
                .iter()
                .filter(|(id, _)| id.as_str() != mol_id.as_str())
                .find(|(_, s)| canonicalize_smiles(s).eq(&normalized))
            {
                duplicates.push(DedupPair {
                    mol_a_id: mol_id.clone(),
                    mol_b_id: match_id.clone(),
                    confidence: 1.0,
                    reason: "exact SMILES match (within batch)".to_string(),
                });
            }
        } else {
            seen_smiles.insert(normalized);
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
                created_at: chrono::Utc::now().to_rfc3339(),
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
    let mut stmt = match conn.prepare("SELECT mol_id, smiles FROM molecules") {
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
                let smiles: String = row.get(1).unwrap_or_default();
                result.push((mol_id, smiles));
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
        created_at: chrono::Utc::now().to_rfc3339(),
    };
    db.add_relation(&rel)
}
