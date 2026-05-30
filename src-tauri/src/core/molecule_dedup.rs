use serde::{Deserialize, Serialize};

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

pub fn find_exact_smiles_match(
    smiles: &str,
    _db: &MoleculeRelationDb,
    existing_mols: &[(String, String)],
) -> Option<(String, f64)> {
    let normalized = canonicalize_smiles(smiles);
    for (mol_id, existing_smiles) in existing_mols {
        if canonicalize_smiles(existing_smiles) == normalized {
            return Some((mol_id.clone(), 1.0));
        }
    }
    None
}

pub fn canonicalize_smiles(smiles: &str) -> String {
    smiles.trim().to_string()
}

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
    val.get("score")
        .and_then(|v| v.as_f64())
        .ok_or_else(|| format!("Invalid tanimoto response: {}", val))
}

pub fn run_dedup_batch(
    new_mols: &[(String, String)],
    db: &MoleculeRelationDb,
    _sidecar_url: &str,
    same_as_threshold: f64,
) -> DedupResult {
    let mut duplicates = Vec::new();
    let mut new_mol_ids = Vec::new();
    let mut relations_added = 0i64;

    for (mol_id, smiles) in new_mols {
        let existing: Vec<(String, String)> = Vec::new();
        if let Some((match_id, conf)) =
            find_exact_smiles_match(smiles, db, &existing)
        {
            duplicates.push(DedupPair {
                mol_a_id: mol_id.clone(),
                mol_b_id: match_id,
                confidence: conf,
                reason: "exact SMILES match".to_string(),
            });
        } else {
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
