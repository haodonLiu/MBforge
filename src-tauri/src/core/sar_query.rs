use serde::{Deserialize, Serialize};

use super::molecule::molecule_db::MoleculeRelationDb;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AnalogWithActivity {
    pub mol_id: String,
    pub esmiles: String,
    pub name: String,
    pub similarity_score: f64,
    pub activity: Option<f64>,
    pub activity_type: String,
    pub units: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScaffoldProfile {
    pub scaffold_esmiles: String,
    pub molecule_count: usize,
    pub activities: Vec<ScaffoldActivityRecord>,
    pub activity_summary: ActivitySummary,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScaffoldActivityRecord {
    pub mol_id: String,
    pub esmiles: String,
    pub name: String,
    pub activity: Option<f64>,
    pub activity_type: String,
    pub units: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ActivitySummary {
    pub count_with_activity: usize,
    pub count_without_activity: usize,
    pub min_activity: Option<f64>,
    pub max_activity: Option<f64>,
    pub mean_activity: Option<f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ActivityCliff {
    pub mol_a_id: String,
    pub mol_b_id: String,
    pub mol_a_esmiles: String,
    pub mol_b_esmiles: String,
    pub mol_a_name: String,
    pub mol_b_name: String,
    pub similarity_score: f64,
    pub activity_a: Option<f64>,
    pub activity_b: Option<f64>,
    pub activity_ratio: Option<f64>,
    pub activity_type: String,
}

pub fn find_analogs_with_activity(
    mol_id: &str,
    min_similarity: f64,
    db: &MoleculeRelationDb,
    molecules_conn: &rusqlite::Connection,
) -> Result<Vec<AnalogWithActivity>, String> {
    let analogs = db
        .find_similar(mol_id, min_similarity)
        .map_err(|e| format!("find_similar failed: {}", e))?;

    let mut results = Vec::new();
    for (rel, score) in analogs {
        let neighbor_id = if rel.mol_a_id == mol_id {
            rel.mol_b_id.clone()
        } else {
            rel.mol_a_id.clone()
        };

        if let Some(record) = get_molecule_activity(&neighbor_id, molecules_conn) {
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

    // TODO-AUDIT: partial_cmp returns None for NaN; unwrap() would panic.
    // If DB contains NaN similarity scores, this will panic. Consider using
    // sorted_by_key with a NaN-aware comparator.
    results.sort_by(|a, b| b.similarity_score.partial_cmp(&a.similarity_score).unwrap());
    Ok(results)
}

pub fn scaffold_activity_profile(
    scaffold_esmiles: &str,
    molecules_conn: &rusqlite::Connection,
) -> Result<ScaffoldProfile, String> {
    let mols = search_molecules_by_scaffold(scaffold_esmiles, molecules_conn)?;

    let mut activities = Vec::new();
    let mut with_act = 0;
    let mut without_act = 0;
    let mut min_act: Option<f64> = None;
    let mut max_act: Option<f64> = None;
    let mut sum_act = 0.0f64;

    for m in &mols {
        if let Some(act) = m.activity {
            with_act += 1;
            sum_act += act;
            min_act = Some(min_act.map(|x| x.min(act)).unwrap_or(act));
            max_act = Some(max_act.map(|x| x.max(act)).unwrap_or(act));
        } else {
            without_act += 1;
        }
        activities.push(ScaffoldActivityRecord {
            mol_id: m.mol_id.clone(),
            esmiles: m.esmiles.clone(),
            name: m.name.clone(),
            activity: m.activity,
            activity_type: m.activity_type.clone(),
            units: m.units.clone(),
        });
    }

    let mean_act = if with_act > 0 {
        Some(sum_act / with_act as f64)
    } else {
        None
    };

    Ok(ScaffoldProfile {
        scaffold_esmiles: scaffold_esmiles.to_string(),
        molecule_count: mols.len(),
        activities,
        activity_summary: ActivitySummary {
            count_with_activity: with_act,
            count_without_activity: without_act,
            min_activity: min_act,
            max_activity: max_act,
            mean_activity: mean_act,
        },
    })
}

pub fn find_activity_cliffs(
    min_similarity: f64,
    min_activity_ratio: f64,
    molecules_conn: &rusqlite::Connection,
) -> Result<Vec<ActivityCliff>, String> {
    let conn = molecules_conn;
    let mut stmt = conn
        .prepare(
            "SELECT * FROM molecule_relations
             WHERE relation_type = 'similar'
               AND score >= ?1
             ORDER BY mol_a_id",
        )
        .map_err(|e| format!("Prepare failed: {}", e))?;
    let mut rows = stmt
        .query(rusqlite::params![min_similarity])
        .map_err(|e| format!("Query failed: {}", e))?;

    let mut cliffs = Vec::new();
    let mut seen: std::collections::HashSet<String> = std::collections::HashSet::new();

    while let Some(row) = rows.next().map_err(|e| format!("Row fetch failed: {}", e))? {
        let mol_a_id: String = row.get(1).unwrap_or_default();
        let mol_b_id: String = row.get(2).unwrap_or_default();
        let score: f64 = row.get(4).unwrap_or(0.0);

        let pair_key = if mol_a_id < mol_b_id {
            format!("{}:{}", mol_a_id, mol_b_id)
        } else {
            format!("{}:{}", mol_b_id, mol_a_id)
        };
        if seen.contains(&pair_key) {
            continue;
        }
        seen.insert(pair_key);

        let mol_a = get_molecule_activity(&mol_a_id, conn);
        let mol_b = get_molecule_activity(&mol_b_id, conn);

        let (act_a, act_b) = (mol_a.as_ref().and_then(|m| m.activity),
                              mol_b.as_ref().and_then(|m| m.activity));

        if let (Some(a), Some(b)) = (act_a, act_b) {
            let ratio = (a / b).max(b / a);
            if ratio >= min_activity_ratio {
                cliffs.push(ActivityCliff {
                    mol_a_id: mol_a_id.clone(),
                    mol_b_id: mol_b_id.clone(),
                    mol_a_esmiles: mol_a.as_ref().map(|m| m.esmiles.clone()).unwrap_or_default(),
                    mol_b_esmiles: mol_b.as_ref().map(|m| m.esmiles.clone()).unwrap_or_default(),
                    mol_a_name: mol_a.as_ref().map(|m| m.name.clone()).unwrap_or_default(),
                    mol_b_name: mol_b.as_ref().map(|m| m.name.clone()).unwrap_or_default(),
                    similarity_score: score,
                    activity_a: Some(a),
                    activity_b: Some(b),
                    activity_ratio: Some(ratio),
                    activity_type: mol_a
                        .as_ref()
                        .map(|m| m.activity_type.clone())
                        .unwrap_or_default(),
                });
            }
        }
    }

    cliffs.sort_by(|a, b| {
        b.activity_ratio
            .partial_cmp(&a.activity_ratio)
            .unwrap_or(std::cmp::Ordering::Equal)
    });
    Ok(cliffs)
}

fn get_molecule_activity(
    mol_id: &str,
    conn: &rusqlite::Connection,
) -> Option<ScaffoldActivityRecord> {
    conn.query_row(
        "SELECT mol_id, esmiles, name, activity, activity_type, units
         FROM molecules WHERE mol_id = ?1",
        rusqlite::params![mol_id],
        |row| {
            Ok(ScaffoldActivityRecord {
                mol_id: row.get(0).unwrap_or_default(),
                esmiles: row.get(1).unwrap_or_default(),
                name: row.get(2).unwrap_or_default(),
                activity: row.get(3).ok(),
                activity_type: row.get(4).unwrap_or_default(),
                units: row.get(5).unwrap_or_default(),
            })
        },
    )
    .ok()
}

fn search_molecules_by_scaffold(
    scaffold_esmiles: &str,
    conn: &rusqlite::Connection,
) -> Result<Vec<ScaffoldActivityRecord>, String> {
    let mut stmt = conn
        .prepare(
            "SELECT mol_id, esmiles, name, activity, activity_type, units
             FROM molecules WHERE esmiles LIKE ?1",
        )
        .map_err(|e| format!("Prepare failed: {}", e))?;
    let pattern = format!("%{}%", scaffold_esmiles);
    let mut rows = stmt
        .query(rusqlite::params![&pattern])
        .map_err(|e| format!("Query failed: {}", e))?;

    let mut results = Vec::new();
    while let Some(row) = rows.next().map_err(|e| format!("Row fetch failed: {}", e))? {
        results.push(ScaffoldActivityRecord {
            mol_id: row.get(0).unwrap_or_default(),
            esmiles: row.get(1).unwrap_or_default(),
            name: row.get(2).unwrap_or_default(),
            activity: row.get(3).ok(),
            activity_type: row.get(4).unwrap_or_default(),
            units: row.get(5).unwrap_or_default(),
        });
    }
    Ok(results)
}
